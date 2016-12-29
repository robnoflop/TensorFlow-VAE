#!/usr/bin/env python

"""
Author: Dan Salo
Initial Commit: 12/1/2016

Purpose: Implement Convolutional VAE for MNIST dataset to demonstrate NNClasses functionality
"""

import sys
sys.path.append('../')

from TensorBase.tensorbase.base import Model
from TensorBase.tensorbase.base import Layers

import tensorflow as tf
import numpy as np
import scipy.misc
import time


# Global Dictionary of Flags
flags = {
    'data_directory': 'MNIST_data/',
    'save_directory': 'summaries/',
    'model_directory': 'conv_vae_proto/',
    'train_data_file': 'mnist_1000_train.tfrecords',
    'valid_data_file': 'mnist_1000_valid.tfrecords',
    'test_data_file': 'mnist_1000_test.tfrecords',
    'num_labels': 1000,
    'restore': False,
    'restore_file': 'start.ckpt',
    'datasets': 'MNIST',
    'image_dim': 28,
    'hidden_size': 10,
    'num_classes': 10,
    'batch_size': 100,
    'display_step': 250,
    'starter_lr': 0.001,
    'num_epochs': 2,
    'weight_decay': 1e-4,
    'run_num': 1,
}


class ConvVae(Model):
    def __init__(self, flags_input, run_num, labeled):
        super().__init__(flags_input, run_num)
        self.print_log("Seed: %d" % flags['seed'])
        self.print_log('Number of Labeled: %d' % labeled)
        self.valid_results = list()
        self.test_results = list()
        names = ['train','valid','test']
        #for n in names:
        #    self.flags[n + '_data_file'] = 'mnist_' +str(labeled) +'_' + n + '.tfrecords'

    def _set_placeholders(self):
        self.epsilon = tf.placeholder(tf.float32, [None, flags['hidden_size']], name='epsilon')
        self.train_x, self.train_y = self.batch_inputs("train")
        self.valid_x, self.valid_y = self.batch_inputs("valid")
        self.test_x, self.test_y = self.batch_inputs("test")
        self.num_train_images = 55000
        self.num_valid_images = 5000
        self.num_test_images = 10000

    @staticmethod
    def img_norm(x, epsilon=1e-6):
        """
        :param x: input feature map stack
        :param scope: name of tensorflow scope
        :param epsilon: float
        :return: output feature map stack
        """
        # Calculate batch mean and variance

        # x = tf.reshape(x, [tf.shape(x)[0],28,28])
        mean, var = tf.nn.moments(x, keep_dims=True)
        out = (x - mean) / tf.sqrt(var + epsilon)
        return tf.expand_dims(out, 3)

    def _set_summaries(self):
        tf.summary.scalar("Total_Loss", self.cost)
        tf.summary.scalar("Reconstruction_Loss", self.recon)
        tf.summary.scalar("VAE_Loss", self.vae)
        tf.summary.scalar("Weight_Decay_Loss", self.weight)
        #tf.summary.scalar("XEntropy_Loss", self.xentropy)
        tf.summary.histogram("Mean", self.mean)
        tf.summary.histogram("Stddev", self.stddev)
        tf.summary.image("train_x", self.train_x)
        tf.summary.image("x_hat", self.x_hat)

    def _encoder(self, x):
        encoder = Layers(x)
        encoder.conv2d(5, 64)
        encoder.maxpool()
        encoder.conv2d(3, 64)
        encoder.conv2d(3, 64)
        encoder.conv2d(3, 128, stride=2)
        encoder.conv2d(3, 128)
        encoder.conv2d(1, 64)
        encoder.conv2d(1, self.flags['hidden_size'] * 2, activation_fn=None)
        encoder.avgpool(globe=True)
        return encoder.get_output()

    def _decoder(self, z):
        if z is None:
            mean = None
            stddev = None
            logits = None
            input_sample = self.epsilon
        else:
            z = tf.reshape(z, [-1, self.flags['hidden_size'] * 2])
            print(z.get_shape())
            mean, stddev = tf.split(1, 2, z)
            stddev = tf.sqrt(tf.exp(stddev))
            logits = tf.nn.softmax(mean)
            input_sample = mean + self.epsilon * stddev
        decoder = Layers(tf.expand_dims(tf.expand_dims(input_sample, 1), 1))
        decoder.deconv2d(3, 128, padding='VALID')
        decoder.deconv2d(3, 128, padding='VALID', stride=2)
        decoder.deconv2d(3, 64, stride=2)
        decoder.deconv2d(3, 64, stride=2)
        decoder.deconv2d(5, 1, activation_fn=tf.nn.tanh, s_value=None)
        return decoder.get_output(), mean, stddev, logits

    def _network(self):
        with tf.variable_scope("model"):
            self.latent = self._encoder(x=self.train_x)
            self.x_hat, self.mean, self.stddev, _ = self._decoder(z=self.latent)
        with tf.variable_scope("model", reuse=True):
            latent_valid = self._encoder(x=self.valid_x)
            _, _, _, self.logits_valid = self._decoder(z=latent_valid)
        with tf.variable_scope("model", reuse=True):
            latent_test = self._encoder(x=self.test_x)
            _, _, _, self.logits_test = self._decoder(z=latent_test)
            self.x_gen, _, _, _ = self._decoder(z=None)

    @staticmethod
    def split_y(logits_y, labels_y):
        for ind in range(labels_y.get_shape()[0]):
            if labels_y[ind] != 10:
                inds.append(ind)
        print(logits_y[inds])
        print(labels_y[inds])
        return logits_y[inds], labels_y[inds]

    def _optimizer(self):
        epsilon = 1e-8
        # self.global_step_var = tf.Variable(0, trainable=False)
        # self.learning_rate = tf.train.exponential_decay(self.flags['starter_lr'], self.global_step_var, 1000, 0.96, staircase=True)
        self.learning_rate = self.flags['starter_lr']
        const = 1/(self.flags['batch_size'] * self.flags['image_dim'] * self.flags['image_dim'])
        self.logits_y = tf.reshape(self.mean, [-1, self.flags['num_classes']])
        #self.xentropy = const * tf.reduce_sum(tf.nn.softmax_cross_entropy_with_logits(self.logits_y, self.train_y, name='xentropy'))
        self.recon = const * tf.reduce_sum(tf.squared_difference(self.train_x, self.x_hat))
        self.vae = const * -0.5 * tf.reduce_sum(1.0 - tf.square(self.mean) - tf.square(self.stddev) + 2.0 * tf.log(self.stddev + epsilon))
        self.weight = self.flags['weight_decay'] * tf.add_n(tf.get_collection('weight_losses'))
        self.cost = tf.reduce_sum(self.vae + self.recon + self.weight)
        self.optimizer = tf.train.AdamOptimizer(learning_rate=self.learning_rate).minimize(self.cost)

    def _run_train_iter(self):
        self.norm = np.random.standard_normal([self.flags['batch_size'], self.flags['hidden_size']])
        self.summary, _ = self.sess.run([self.merged, self.optimizer], feed_dict={self.epsilon: self.norm})

    def _run_train_summary_iter(self):
        self.norm = np.random.standard_normal([self.flags['batch_size'], self.flags['hidden_size']])
        self.summary, self.loss, self.x_recon, _ = self.sess.run([self.merged, self.cost, self.x_hat, self.optimizer], feed_dict={self.epsilon: self.norm})

    def training(self):
        self.step = 0
        threads = tf.train.start_queue_runners(sess=self.sess)
        coord = tf.train.Coordinator()
        for i in range(550 * 1):
            start_time = time.time()
            self._run_train_iter()
            self.duration = time.time() - start_time

            if self.step % self.flags['display_step'] == 0:
                self._run_train_summary_iter()
                self._record_training_step()
                self._record_train_metrics()
            self.step += 1
            print(self.step)
        self.print_log('Done training for %d epochs, %d steps.' % (self.flags['num_epochs'], self.step))
        coord.request_stop()
        self._save_model(section=1)        

        # Wait for threads to finish.
        coord.join(threads)
        self.sess.close()

    def train_ing(self):
        self.step = 0
        threads = tf.train.start_queue_runners(sess=self.sess)
        coord = tf.train.Coordinator()
        try:
            while not coord.should_stop():
                start_time = time.time()
                self._run_train_iter()
                self.duration = time.time() - start_time

                if self.step % self.flags['display_step'] == 0:
                    self._run_train_summary_iter()
                    self._record_training_step()
                    self._record_train_metrics()
                self.step += 1
                print(self.step)
        except tf.errors.OutOfRangeError:
            self.print_log('Done training for %d epochs, %d steps.' % (self.flags['num_epochs'], self.step))
        finally:
            # When done, ask the threads to stop.
            coord.request_stop()
        self._save_model(section=1)        

        # Wait for threads to finish.
        coord.join(threads)
        self.sess.close()
    

    def validate(self):
        self.step = 0
        threads = tf.train.start_queue_runners(sess=self.sess)
        coord = tf.train.Coordinator()
        try:
            while not coord.should_stop():
                logits, true = self.sess.run([self.logits_valid, self.valid_y])
                predictions = np.reshape(logits, [-1, self.flags['num_classes']])
                correct_prediction = np.equal(true, np.argmax(predictions, 1))
                self.valid_results = np.concatenate((self.valid_results, correct_prediction))
        except tf.errors.OutOfRangeError:
            self.print_log('Done training for %d epochs, %d steps.' % (self.flags['num_epochs'], self.step))
        finally:
            # When done, ask the threads to stop.
            coord.request_stop()      

        # Wait for threads to finish.
        self._record_valid_metrics()        
        coord.join(threads)
        self.sess.close()

    def testing(self):
        self.step = 0
        threads = tf.train.start_queue_runners(sess=self.sess)
        coord = tf.train.Coordinator()
        try:
            while not coord.should_stop():
                logits, true = self.sess.run([self.logits_valid, self.valid_y])
                predictions = np.reshape(logits, [-1, self.flags['num_classes']])
                correct_prediction = np.equal(true, np.argmax(predictions, 1))
                self.valid_results = np.concatenate((self.valid_results, correct_prediction))
        except tf.errors.OutOfRangeError:
            self.print_log('Done training for %d epochs, %d steps.' % (self.flags['num_epochs'], self.step))
        finally:
            # When done, ask the threads to stop.
            coord.request_stop() 
        self._record_test_metrics()
        coord.join(threads)
        self.sess.close()

    def _record_train_metrics(self):
        train_images = self.sess.run([self.train_x])
        for j in range(1):
            scipy.misc.imsave(self.flags['restore_directory'] + 'x_' + str(self.step) + '.png',
                              np.squeeze(train_images)[j])
            scipy.misc.imsave(self.flags['restore_directory'] + 'x_recon_' + str(self.step) + '.png',
                              np.squeeze(self.x_recon[j]))
        self.print_log('Learning Rate: %d' % self.learning_rate)
        self.print_log('Step %d: loss = %.6f (%.3f sec)' % (self.step,self.loss,self.duration))

    def _record_valid_metrics(self):
        accuracy = np.mean(self.valid_results)
        self.print_log("Accuracy on Validation Set: %f" % accuracy)
        file = open(self.flags['restore_directory'] + 'ValidAccuracy.txt', 'w')
        file.write('Test set accuracy:')
        file.write(str(accuracy))
        file.close()

    def _record_test_metrics(self):
        accuracy = np.mean(self.test_results)
        self.print_log("Accuracy on Test Set: %f" % accuracy)
        file = open(self.flags['restore_directory'] + 'TestAccuracy.txt', 'w')
        file.write('Test set accuracy:')
        file.write(str(accuracy))
        file.close()
    
    def batch_inputs(self, dataset, num_preprocess_threads=4, num_readers=4):
        with tf.name_scope('batch_processing'):
            # Create filename_queue
            if dataset == "train":
                filename_queue = tf.train.string_input_producer([self.flags['train_data_file']],
                                  shuffle=True,
                                  capacity=16)
            else:
                filename_queue = tf.train.string_input_producer([self.flags[dataset + '_data_file']],
                                  shuffle=False,
                                  capacity=1)

            # Approximate number of examples per shard.
            examples_per_shard = 1024
            # Size the random shuffle queue to balance between good global
            # mixing (more examples) and memory use (fewer examples).
            # 1 image uses 299*299*3*4 bytes = 1MB
            # The default input_queue_memory_factor is 16 implying a shuffling queue
            # size: examples_per_shard * 16 * 1MB = 17.6GB
            min_queue_examples = examples_per_shard * 16
            if dataset == "train":
                examples_queue = tf.RandomShuffleQueue(capacity=min_queue_examples + 3 *  self.flags['batch_size'],
                    min_after_dequeue=min_queue_examples,
                    dtypes=[tf.string])
            else:
                examples_queue = tf.FIFOQueue(capacity=examples_per_shard + 3 * self.flags['batch_size'], dtypes=[tf.string])

        # Create multiple readers to populate the queue of examples.
        if num_readers > 1:
            enqueue_ops = list()
            for _ in range(num_readers):
                reader = tf.TFRecordReader()
                _, value = reader.read(filename_queue)
                enqueue_ops.append(examples_queue.enqueue([value]))

                tf.train.queue_runner.add_queue_runner(tf.train.queue_runner.QueueRunner(examples_queue, enqueue_ops))
                example_serialized = examples_queue.dequeue()
        else:
           reader = tf.TFRecordReader()
           _, example_serialized = reader.read(filename_queue)

        images_and_labels = list()
        for _ in range(num_preprocess_threads):
            # Parse a serialized Example proto to extract the image and metadata.
            image, label = self.read_and_decode(example_serialized)
            images_and_labels.append([image, label])

        image_batch, label_batch = tf.train.batch_join(images_and_labels, batch_size=self.flags['batch_size'], capacity=2 * num_preprocess_threads * self.flags['batch_size'])
        return image_batch, label_batch

    def read_and_decode(self, example_serialized):
        features = tf.parse_single_example(
            example_serialized,
            features={
                'image': tf.FixedLenFeature([], tf.string),
                'label': tf.FixedLenFeature([self.flags['num_classes']], tf.int64, default_value=[-1]*self.flags['num_classes']),
                'height': tf.FixedLenFeature([], tf.int64),
                'width': tf.FixedLenFeature([], tf.int64),
                'depth': tf.FixedLenFeature([], tf.int64),
            })
        # now return the converted data
        label = features['label']
        image = tf.decode_raw(features['image'], tf.float32)
        image.set_shape([784])
        image = tf.reshape(image, [28, 28, 1])
        return tf.cast(image, tf.float32), tf.cast(label, tf.int32)

def main():
    flags['seed'] = np.random.randint(1, 1000, 1)[0]
    counter = 1
    model_vae = ConvVae(flags, run_num=counter, labeled=1000)
    model_vae.training()
"""
    for l in [100, 300, 1000, 5000]:
        model_vae = ConvVae(flags, run_num=counter, labeled=l)
        counter += 1
"""

if __name__ == "__main__":
    main()
