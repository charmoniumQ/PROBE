#!/usr/bin/env python

import argparse

import matplotlib.pyplot as plt
import tensorflow as tf
import tensorflow_text
import sys
import pathlib
root = pathlib.Path(__file__).resolve().parent.resolve()
sys.path.insert(0, str(root))
import components

parser = argparse.ArgumentParser()
parser.add_argument('--num-layers', type=int, default=4)
parser.add_argument('--d-model', type=int, default=128)
parser.add_argument('--dff', type=int, default=512)
parser.add_argument('--num-heads', type=int, default=8)
parser.add_argument('--dropout-rate', type=float, default=0.1)
parser.add_argument('--epochs', type=int, default=1)
parser.add_argument('--warmup-steps', type=int, default=4000)
parser.add_argument('--data-dir', default='/workload_output')
args = parser.parse_args()

train_batches = tf.data.Dataset.load(args.data_dir + '/train_batches')
val_batches = tf.data.Dataset.load(args.data_dir + '/val_batches')


d_model = args.d_model
learning_rate = components.CustomSchedule(d_model, warmup_steps=args.warmup_steps)

optimizer = tf.keras.optimizers.Adam(learning_rate, beta_1=0.9, beta_2=0.98,
                                     epsilon=1e-9)


# Test the custom learning rate scheduler:

# In[ ]:


plt.plot(learning_rate(tf.range(40000, dtype=tf.float32)))
plt.ylabel('Learning Rate')
plt.xlabel('Train Step')


def masked_loss(label, pred):
  mask = label != 0
  loss_object = tf.keras.losses.SparseCategoricalCrossentropy(
    from_logits=True, reduction='none')
  loss = loss_object(label, pred)

  mask = tf.cast(mask, dtype=loss.dtype)
  loss *= mask

  loss = tf.reduce_sum(loss)/tf.reduce_sum(mask)
  return loss


def masked_accuracy(label, pred):
  pred = tf.argmax(pred, axis=2)
  label = tf.cast(label, pred.dtype)
  match = label == pred

  mask = label != 0

  match = match & mask

  match = tf.cast(match, dtype=tf.float32)
  mask = tf.cast(mask, dtype=tf.float32)
  return tf.reduce_sum(match)/tf.reduce_sum(mask)


model_name = 'ted_hrlr_translate_pt_en_converter'
tokenizers = tf.saved_model.load(args.data_dir + f'/{model_name}_extracted/{model_name}')

transformer = components.Transformer(
    num_layers=args.num_layers,
    d_model=args.d_model,
    num_heads=args.num_heads,
    dff=args.dff,
    input_vocab_size=tokenizers.pt.get_vocab_size().numpy(),
    target_vocab_size=tokenizers.en.get_vocab_size().numpy(),
    dropout_rate=args.dropout_rate)

# output = transformer((pt, en))

# print(en.shape)
# print(pt.shape)
# print(output.shape)


# attn_scores = transformer.decoder.dec_layers[-1].last_attn_scores
# print(attn_scores.shape)
# (batch, heads, target_seq, input_seq)


transformer.compile(
    loss=masked_loss,
    optimizer=optimizer,
    metrics=[masked_accuracy])


transformer.fit(train_batches,
                epochs=args.epochs,
                validation_data=val_batches)

transformer.save(args.data_dir + '/trained_model.keras')
transformer.save_weights(args.data_dir + '/trained_model.weights.h5')
print('Trained model weights saved.')
