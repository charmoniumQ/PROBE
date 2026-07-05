#!/usr/bin/env python

import tensorflow_datasets as tfds
import tensorflow as tf

from tensorflow_datasets.datasets.ted_hrlr_translate import ted_hrlr_translate_dataset_builder
ted_hrlr_translate_dataset_builder._DATA_URL = (
    "https://web.archive.org/web/20240301220426if_/http://www.phontron.com/data/qi18naacl-dataset.tar.gz"
)

(train_examples, val_examples), metadata = tfds.load(
    'ted_hrlr_translate/pt_to_en',
    split=['train[:1%]', 'validation[:1%]'],
    with_info=True,
    as_supervised=True,
    data_dir="/scratch/data"
)

tf.data.Dataset.save(train_examples, '/scratch/train_examples')
tf.data.Dataset.save(val_examples, '/scratch/val_examples')

for pt_examples, en_examples in train_examples.batch(3).take(1):
    print('> Examples in Portuguese:')
    for pt in pt_examples.numpy():
        print(pt.decode('utf-8'))
    print()
    print('> Examples in English:')
    for en in en_examples.numpy():
        print(en.decode('utf-8'))
