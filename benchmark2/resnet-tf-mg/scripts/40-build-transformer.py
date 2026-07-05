#!/usr/bin/env python

import pickle
import tensorflow as tf
import tensorflow_text

import sys
import pathlib
root = pathlib.Path(__file__).resolve().parent.resolve()
sys.path.insert(0, str(root))
import components

train_batches = tf.data.Dataset.load('/scratch/train_batches')
val_batches = tf.data.Dataset.load('/scratch/val_batches')


for (pt, en), en_labels in train_batches.take(1):
    break


print(pt.shape)
print(en.shape)
print(en_labels.shape)
print(en[0][:10])
print(en_labels[0][:10])


model_name = 'ted_hrlr_translate_pt_en_converter'
tokenizers = tf.saved_model.load(f'/scratch/{model_name}_extracted/{model_name}')

embed_pt = components.PositionalEmbedding(vocab_size=tokenizers.pt.get_vocab_size().numpy(), d_model=512)
embed_en = components.PositionalEmbedding(vocab_size=tokenizers.en.get_vocab_size().numpy(), d_model=512)

pt_emb = embed_pt(pt)
en_emb = embed_en(en)

sample_ca = components.CrossAttention(num_heads=2, key_dim=512)

print(pt_emb.shape)
print(en_emb.shape)
print(sample_ca(en_emb, pt_emb).shape)

sample_gsa = components.GlobalSelfAttention(num_heads=2, key_dim=512)

print(pt_emb.shape)
print(sample_gsa(pt_emb).shape)

sample_csa = components.CausalSelfAttention(num_heads=2, key_dim=512)

print(en_emb.shape)
print(sample_csa(en_emb).shape)


sample_csa = components.CausalSelfAttention(num_heads=2, key_dim=512)

print(en_emb.shape)
print(sample_csa(en_emb).shape)


out1 = sample_csa(embed_en(en[:, :3])) 
out2 = sample_csa(embed_en(en))[:, :3]

tf.reduce_max(abs(out1 - out2)).numpy()


sample_ffn = components.FeedForward(512, 2048)

print(en_emb.shape)
print(sample_ffn(en_emb).shape)

sample_encoder_layer = components.EncoderLayer(d_model=512, num_heads=8, dff=2048)

print(pt_emb.shape)
print(sample_encoder_layer(pt_emb).shape)

# Instantiate the encoder.
sample_encoder = components.Encoder(num_layers=4,
                         d_model=512,
                         num_heads=8,
                         dff=2048,
                         vocab_size=8500)

sample_encoder_output = sample_encoder(pt, training=False)

# Print the shape.
print(pt.shape)
print(sample_encoder_output.shape)  # Shape `(batch_size, input_seq_len, d_model)`.

sample_decoder_layer = components.DecoderLayer(d_model=512, num_heads=8, dff=2048)

sample_decoder_layer_output = sample_decoder_layer(
    x=en_emb, context=pt_emb)

print(en_emb.shape)
print(pt_emb.shape)
print(sample_decoder_layer_output.shape)  # `(batch_size, seq_len, d_model)`


# Instantiate the decoder.
sample_decoder = components.Decoder(num_layers=4,
                         d_model=512,
                         num_heads=8,
                         dff=2048,
                         vocab_size=8000)

output = sample_decoder(
    x=en,
    context=pt_emb)

# Print the shapes.
print(en.shape)
print(pt_emb.shape)
print(output.shape)
