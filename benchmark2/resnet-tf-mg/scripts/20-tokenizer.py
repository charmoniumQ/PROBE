#!/usr/bin/env python

import numpy as np
import matplotlib.pyplot as plt

import tensorflow as tf
import tensorflow_text

train_examples = tf.data.Dataset.load('train_examples')
val_examples = tf.data.Dataset.load('val_examples')

model_name = 'ted_hrlr_translate_pt_en_converter'
tf.keras.utils.get_file(
    f'{model_name}.zip',
    f'https://storage.googleapis.com/download.tensorflow.org/models/{model_name}.zip',
    cache_dir='/scratch/', cache_subdir='', extract=True
)

tokenizers = tf.saved_model.load(f'/scratch/{model_name}_extracted/{model_name}')

print([item for item in dir(tokenizers.en) if not item.startswith('_')])

for pt_examples, en_examples in train_examples.batch(3).take(1):
    pass

print('> This is a batch of strings:')
for en in en_examples.numpy():
    print(en.decode('utf-8'))

encoded = tokenizers.en.tokenize(en_examples)
print('> This is a padded-batch of token IDs:')
for row in encoded.to_list():
    print(row)

round_trip = tokenizers.en.detokenize(encoded)
print('> This is human-readable text:')
for line in round_trip.numpy():
    print(line.decode('utf-8'))

print('> This is the text split into tokens:')
tokens = tokenizers.en.lookup(encoded)
print(tokens)

lengths = []
for pt_examples, en_examples in train_examples.batch(1024):
    pt_tokens = tokenizers.pt.tokenize(pt_examples)
    lengths.append(pt_tokens.row_lengths())
    en_tokens = tokenizers.en.tokenize(en_examples)
    lengths.append(en_tokens.row_lengths())
    print('.', end='', flush=True)
print()

all_lengths = np.concatenate(lengths)
plt.hist(all_lengths, np.linspace(0, 500, 101))
plt.ylim(plt.ylim())
max_length = max(all_lengths)
plt.plot([max_length, max_length], plt.ylim())
plt.title(f'Maximum tokens per example: {max_length}')
