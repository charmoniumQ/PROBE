import tensorflow as tf
import tensorflow_text

train_examples = tf.data.Dataset.load('train_examples')
val_examples = tf.data.Dataset.load('val_examples')
model_name = 'ted_hrlr_translate_pt_en_converter'
tokenizers = tf.saved_model.load(f'/scratch/{model_name}_extracted/{model_name}')

MAX_TOKENS = 128
def prepare_batch(pt, en):
    pt = tokenizers.pt.tokenize(pt)
    pt = pt[:, :MAX_TOKENS]
    pt = pt.to_tensor()
    en = tokenizers.en.tokenize(en)
    en = en[:, :(MAX_TOKENS+1)]
    en_inputs = en[:, :-1].to_tensor()
    en_labels = en[:, 1:].to_tensor()
    return (pt, en_inputs), en_labels

BUFFER_SIZE = 20000
BATCH_SIZE = 64

def make_batches(ds):
    return (
        ds
        .shuffle(BUFFER_SIZE)
        .batch(BATCH_SIZE)
        .map(prepare_batch, tf.data.AUTOTUNE)
        .prefetch(buffer_size=tf.data.AUTOTUNE)
    )

train_batches = make_batches(train_examples)
val_batches = make_batches(val_examples)

tf.data.Dataset.save(train_batches, '/scratch/train_batches')
tf.data.Dataset.save(val_batches, '/scratch/val_batches')
