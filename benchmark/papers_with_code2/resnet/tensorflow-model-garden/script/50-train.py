#!/usr/bin/env python

import matplotlib.pyplot as plt
import tensorflow as tf
import tensorflow_text
import components

train_batches = tf.data.Dataset.load('train_batches')
val_batches = tf.data.Dataset.load('val_batches')


# Instantiate the optimizer (in this example it's `tf.keras.optimizers.Adam`):

# In[ ]:


d_model = 128
learning_rate = components.CustomSchedule(d_model)

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


num_layers = 4
d_model = 128
dff = 512
num_heads = 8
dropout_rate = 0.1

model_name = 'ted_hrlr_translate_pt_en_converter'
tokenizers = tf.saved_model.load(f'{model_name}_extracted/{model_name}')

transformer = components.Transformer(
    num_layers=num_layers,
    d_model=d_model,
    num_heads=num_heads,
    dff=dff,
    input_vocab_size=tokenizers.pt.get_vocab_size().numpy(),
    target_vocab_size=tokenizers.en.get_vocab_size().numpy(),
    dropout_rate=dropout_rate)

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
                epochs=1,
                validation_data=val_batches)

transformer.save('trained_model.keras')
transformer.save_weights('trained_model.weights.h5')
print('Trained model weights saved.')
