# -*- coding: utf-8 -*-
"""
Created on Mon Jan 28 22:51:54 2019

@author: Vaaan
"""

import numpy as np
import re
import tensorflow as tf
import time

# Open the datasets
movie_lines = open(
        'movie_lines.txt',
        encoding='utf-8',
        errors='ignore').read().split('\n')
movie_conversations = open(
        'movie_conversations.txt',
        encoding='utf-8',
        errors='ignore').read().split('\n')

# Create dictionary of the movie lines and it's id
id_to_line = {}
for line in movie_lines:
    _line = line.split(' +++$+++ ')
    if len(_line) == 5:
        id_to_line[_line[0]] = _line[4]
        
# Create list of conversation id's
conversation_ids = []
for conversation in movie_conversations[:-1]:
    _conversation = conversation.split(' +++$+++ ')[-1][1:-1].replace("'", "").replace(" ", "")
    conversation_ids.append(_conversation.split(','))
    
# Separate the question and answer
questions = []
answers = []
for conversation in conversation_ids:
    for i in range(len(conversation) - 1):
        questions.append(id_to_line[conversation[i]])
        answers.append(id_to_line[conversation[i+1]])
        
def clean(text):
    text = text.lower()
    text = re.sub(r"i'm", 'i am', text)
    text = re.sub(r"he's", 'he is', text)
    text = re.sub(r"she's", 'she is', text)
    text = re.sub(r"that's", 'that is', text)
    text = re.sub(r"what's", 'what is', text)
    text = re.sub(r"where's", 'where is', text)
    text = re.sub(r"how's", 'how is', text)
    text = re.sub(r"here's", 'here is', text)
    
    text = re.sub(r"\'ll", ' will', text)
    text = re.sub(r"\'ve", ' have', text)
    text = re.sub(r"\'re", ' you are', text)
    text = re.sub(r"\'d", ' would', text)
    
    text = re.sub(r"won't", 'will not', text)
    text = re.sub(r"can't", 'can not', text)
    text = re.sub(r"[-()\"#/@;:<>{}+=~|.?,]", '', text)
                     
    return text

# Clean Questions
cleaned_questions = []
for question in questions:
    cleaned_questions.append(clean(question))
    
# Clean Answers
cleaned_answers = []
for answer in answers:
    cleaned_answers.append(clean(answer))
    
# Dictionary of word with it's number of occurences
word_to_count = {}
for question in cleaned_questions:
    for word in question.split():
        if word not in word_to_count:
            word_to_count[word] = 1
        else:
            word_to_count[word] += 1

for answer in cleaned_answers:
    for word in question.split():
        if word not in word_to_count:
            word_to_count[word] = 1
        else:
            word_to_count[word] += 1

# Dictionary that map the questions words and the answer words to a unique key
threshold = 20

question_words_to_int = {}
counter = 0
for word, word_count in word_to_count.items():
    if word_count >= threshold:
        question_words_to_int[word] = counter
        counter += 1
        
answer_words_to_int = {}
counter = 0
for word, word_count in word_to_count.items():
    if word_count >= threshold:
        answer_words_to_int[word] = counter
        counter += 1


# Add Token to the two dictionary for encoder & decoder
tokens = ['<PAD>', '<EOS>', '<OUT>', '<SOS>']
for token in tokens:
    question_words_to_int[token] = len(question_words_to_int) + 1
    answer_words_to_int[token] = len(answer_words_to_int) + 1


# Inverse answer_words_to_int dictionary
answers_int_to_word = {word_int: word for word, word_int in answer_words_to_int.items()}


# Translate all the questions and the answers into unique key
# And replace all the words that were filtered by <OUT>
question_to_int = []
for question in cleaned_questions:
    question_ints = []
    for word in question.split():
        if word not in question_words_to_int:
            question_ints.append(question_words_to_int['<OUT>'])
        else:
            question_ints.append(question_words_to_int[word])
            
    question_to_int.append(question_ints)

answer_to_int = []
for answer in cleaned_answers:
    answer_ints = []
    for word in answer.split():
        if word not in answer_words_to_int:
            answer_ints.append(answer_words_to_int['<OUT>'])
        else:
            answer_ints.append(answer_words_to_int[word])
            
    answer_to_int.append(answer_ints)

# Sort question and answers by length of question to speed up the training
max_length_of_question = 25
sorted_cleaned_questions = []
sorted_cleaned_answers = []
for length in range(1, max_length_of_question + 1):
    for i, value in enumerate(question_to_int):
        if len(value) == length:
            sorted_cleaned_questions.append(question_to_int[i])
            sorted_cleaned_answers.append(answer_to_int[i])

# Create placeholder for the inputs and targets
def model_inputs():
    inputs = tf.placeholder(tf.int32, [None, None], name='input')
    targets = tf.placeholder(tf.int32, [None, None], name='target') # targets or answer
    learning_rate = tf.placeholder(tf.float32, name='learning_rate')
    keep_prob = tf.placeholder(tf.float32, name='keep_prob')
    return inputs, targets, learning_rate, keep_prob

# Preprocess the targets
def preprocess_targets(targets, answer_words_to_int, batch_size):
    left_side = tf.fill([batch_size, 1], answer_words_to_int['<SOS>'])
    right_side = tf.strided_slice(targets, [0,0], [batch_size,-1], [1,1])
    preprocessed_target = tf.concat([left_side, right_side], 1)
    return preprocessed_target

# RNN Encoder Layer
def encoder_rnn(rnn_inputs, rnn_size, num_layers, keep_prob, sequence_length):
    lstm = tf.contrib.rnn.BasicLSTMCell(rnn_size)
    lstm_dropout = tf.contrib.rnn.DropoutWrapper(lstm, keep_prob)
    encoder_cell = tf.contrib.rnn.MultiRNNCell([lstm_dropout] * num_layers)
    _encoder_output, encoder_state = tf.nn.bidirectional_dynamic_rnn(cell_fw=encoder_cell,
                                                       cell_bw=encoder_cell,
                                                       sequence_length=sequence_length,
                                                       inputs=rnn_inputs,
                                                       dtype=tf.float32)
    return encoder_state

# Decoding the training set
def decode_training_set(encoder_state, decoder_cell, decoder_embedded_input, sequence_length,
                        decoding_scope, output_function, keep_prob, batch_size):
    attention_state = tf.zeros([batch_size, 1, decoder_cell.output_size])
    attention_keys, attention_values, attention_score_function, \
    attention_construct_function = tf.contrib.seq2seq.prepare_attention(
            attention_state,
            attention_option='bahdanau',
            num_units=decoder_cell.output_size)
    training_decoder_function = tf.contrib.seq2seq.attention_decoder_fn_train(
            encoder_state[0],
            attention_keys,
            attention_values,
            attention_score_function,
            attention_construct_function,
            name='attn_dec_train')
    
    decoder_output, _decoder_final_state, \
    _decoder_context_state = tf.contrib.seq2seq.dynamic_rnn_decoder(
            decoder_cell,
            training_decoder_function,
            decoder_embedded_input,
            sequence_length,
            scope=decoding_scope)
    
    decoder_output_dropout = tf.nn.dropout(decoder_output, keep_prob)
    
    return output_function(decoder_output_dropout)


# Decoding test/validation set
def decode_test_set(encoder_state, decoder_cell, decoder_embeddings_matrix,
                    sequence_length,
                    decoding_scope, output_function, keep_prob, batch_size,
                    sos_id, eos_id, max_length, num_words):
    attention_state = tf.zeros([batch_size, 1, decoder_cell.output_size])
    attention_keys, attention_values, attention_score_function, \
    attention_construct_function = tf.contrib.seq2seq.prepare_attention(
            attention_state,
            attention_option='bahdanau',
            num_units=decoder_cell.output_size)
    
    test_decoder_function = tf.contrib.seq2seq.attention_decoder_fn_inference(
            output_function,
            encoder_state[0],
            attention_keys,
            attention_values,
            attention_score_function,
            attention_construct_function,
            decoder_embeddings_matrix,
            sos_id,
            eos_id,
            max_length,
            num_words,
            name='attn_dec_inference')
    
    text_predictions, _decoder_final_state, \
    _decoder_context_state = tf.contrib.seq2seq.dynamic_rnn_decoder(
            decoder_cell,
            test_decoder_function,
            scope=decoding_scope)
    
    return text_predictions

# Decoder RNN
def decoder_rnn(decoder_embedded_input, decoder_embeddings_matrix, encoder_state,
                num_words, sequence_length, rnn_size, num_layers, word_to_int,
                keep_prob, batch_size):
    with tf.variable_scope("decoding") as decoding_scope:
        lstm = tf.contrib.rnn.BasicLSTMCell(rnn_size)
        lstm_dropout = tf.contrib.rnn.DropoutWrapper(lstm, keep_prob)
        decoder_cell = tf.contrib.rnn.MultiRNNCell([lstm_dropout] * num_layers)
        
        weights = tf.truncated_normal_initializer(stddev=0.1)
        biases = tf.zeros_initializer()
        
        output_function = lambda x: tf.contrib.layers.fully_connected(x,
                                                                      num_words,
                                                                      None,
                                                                      scope=decoding_scope,
                                                                      weights_initializer=weights,
                                                                      biases_initializer=biases)
        training_predictions = decode_training_set(encoder_state, decoder_cell,
                                                  decoder_embedded_input, sequence_length,
                                                  decoding_scope, output_function,
                                                  keep_prob, batch_size)
        decoding_scope.reuse_variables()
        test_predictions = decode_test_set(encoder_state, decoder_cell,
                                           decoder_embeddings_matrix, sequence_length,
                                           decoding_scope, output_function,
                                           keep_prob, batch_size,
                                           word_to_int['<SOS>'], word_to_int['<EOS>'],
                                           sequence_length-1, num_words)
        
    
    return training_predictions, test_predictions

# Seq2Seq Model
def seq_to_seq_model(inputs, targets, keep_prob, batch_size, sequence_length,
                     answers_num_words, questions_num_words, encoder_embedding_size,
                     decoder_embedding_size, rnn_size, num_layers, questions_words_to_int):
    encoder_embedded_input = tf.contrib.layers.embed_sequence(inputs,
                                                              answers_num_words+1,
                                                              encoder_embedding_size,
                                                              initializer=tf.random_uniform_initializer(0, 1))
    encoder_state = encoder_rnn(encoder_embedded_input, rnn_size, num_layers,
                                keep_prob, sequence_length)
    preprocessed_targets = preprocess_targets(targets, questions_words_to_int, batch_size)
    decoder_embeddings_matrix = tf.Variable(
            tf.random_uniform([questions_num_words+1, decoder_embedding_size], 0, 1))
    decoder_embedded_input = tf.nn.embedding_lookup(decoder_embeddings_matrix, preprocessed_targets)
    
    training_predictions, test_predictions = decoder_rnn(decoder_embedded_input,
                                                         decoder_embeddings_matrix,
                                                         encoder_state,
                                                         questions_num_words,
                                                         sequence_length,
                                                         rnn_size,
                                                         num_layers,
                                                         questions_words_to_int,
                                                         keep_prob,
                                                         batch_size)
    return training_predictions, test_predictions


# Hyperparameters
epochs = 100
batch_size = 64
rnn_size = 512
num_layers = 3
encoding_embedding_size = 512
decoding_embedding_size = 512
learning_rate = 0.015
learning_rate_decay = 0.9
minimum_learning_rate = 0.0001
keep_probability = 0.5

# Tensorflow Session
tf.reset_default_graph()
session = tf.InteractiveSession()

inputs, targets, lr, keep_prob = model_inputs()

# Set sequence length
sequence_length = tf.placeholder_with_default(25, None, name='sequence_length')

# Get Shape of inputs tensor
input_shape = tf.shape(inputs)

# Get training and test predictions
training_prediction, test_predictions = seq_to_seq_model(
            tf.reverse(inputs, [-1]),
            targets,
            keep_probability,
            batch_size,
            sequence_length,
            len(answer_words_to_int),
            len(question_words_to_int),
            encoding_embedding_size,
            decoding_embedding_size,
            rnn_size, 
            num_layers,
            question_words_to_int
        )

# Loss Error, Optimizer & Gradient Clipping
with tf.name_scope('optimization'):
    loss_error = tf.contrib.seq2seq.sequence_loss(training_prediction,
                                                  targets,
                                                  tf.ones([input_shape[0], sequence_length]))
    
    optimizer = tf.train.AdamOptimizer(learning_rate)
    gradients = optimizer.compute_gradients(loss_error)
    clipped_gradients = [
            (tf.clip_by_value(grad_tensor, -5., 5.), grad_variable) 
            for grad_tensor, grad_variable in gradients if grad_tensor is not None]
    
    optimizer_gradient_clipping = optimizer.apply_gradients(clipped_gradients)

# Padding the sequence with the <PAD> token so the length of both question
# and answer is of the same length
def apply_padding(batch_of_sequence, word_to_int):
    max_sequence_length = max([len(sequence) for sequence in batch_of_sequence])
    return [sequence + [word_to_int['<PAD>']] * (max_sequence_length - len(sequence)) 
            for sequence in batch_of_sequence]  

# Split the data into batches of question and asnwers
def split_to_batches(questions, answers, batch_size):
    for i in range(0, len(questions) // batch_size):
        start_index = i * batch_size
        questions_in_batch = questions[start_index:start_index+batch_size]
        answers_in_batch = answers[start_index:start_index+batch_size]
        
        padded_questions = np.array(apply_padding(questions_in_batch, question_words_to_int))
        padded_answers = np.array(apply_padding(answers_in_batch, answer_words_to_int))
        
        yield padded_questions, padded_answers

# Split the question and answer for training and validation
training_validation_index = int(len(sorted_cleaned_questions) * 0.15)

training_questions = sorted_cleaned_questions[training_validation_index:]
training_answers = sorted_cleaned_answers[training_validation_index:]

validation_questions = sorted_cleaned_questions[:training_validation_index]
validation_answers = sorted_cleaned_answers[:training_validation_index]

# Training
batch_index_check_training_loss = 100 # Check training loss every 100 batches
batch_index_check_validation_loss = (len(training_questions) // batch_size // 2) - 1

total_training_loss_error = 0

list_validation_loss_error = []

early_stopping_check = 0
early_stopping_index = 1000

checkpoint = "chatbot_weight.ckpt"

session.run(tf.global_variables_initializer())
    
for epoch in range(1, epochs + 1):
    for batch_index, (padded_questions, padded_answers) \
    in enumerate(split_to_batches(training_questions, training_answers, batch_size)):
        starting_time = time.time()
        _, batch_training_loss_error = session.run(
                [optimizer_gradient_clipping, loss_error],
                {
                    inputs:padded_questions,
                    targets:padded_answers, 
                    lr:learning_rate,
                    sequence_length: padded_answers.shape[1],
                    keep_prob: keep_probability
                })
        total_training_loss_error += batch_training_loss_error
        ending_time = time.time()
        batch_training_time = ending_time - starting_time
        if batch_index % batch_index_check_training_loss == 0:
            print(
                'Epoch:{:>3}/{}, Batch:{:>4}/{}, Training Loss Error:{:>6.3f},'\
                'Training time on 100 Batches:{:d} seconds'.format(
                                                                    epoch,epochs,
                                                                    batch_index,
                                                                    len(training_questions)//batch_size,
                                                                    total_training_loss_error / batch_index_check_training_loss,
                                                                    int(batch_training_time * batch_index_check_training_loss))
                )
            total_training_loss_error = 0
        
        if batch_index % batch_index_check_validation_loss == 0 and batch_index > 0:
            total_validation_loss_error = 0
            starting_time = time.time()
            
            for batch_index_validation, (padded_questions, padded_answers) \
            in enumerate(split_to_batches(validation_questions, validation_answers, batch_size)):
                batch_validation_loss_error = session.run(
                loss_error,
                {
                    inputs:padded_questions,
                    targets:padded_answers, 
                    learning_rate:learning_rate,
                    sequence_length: padded_answers.shape[1],
                    keep_prob: 1
                })
                total_validation_loss_error += batch_validation_loss_error
            ending_time = time.time()
            batch_validation_time = ending_time - starting_time
            average_validation_loss_error = total_validation_loss_error / (len(validation_questions) / batch_size)
            print('Validation Loss Error:{:>6.3f}, Batch Validation Time:{:d} seconds'.format(average_validation_loss_error, int(batch_validation_time)))
            
            learning_rate *= learning_rate_decay
            if learning_rate < minimum_learning_rate:
                learning_rate = minimum_learning_rate
                
            list_validation_loss_error.append(average_validation_loss_error)
            # if average validation loss error is less than the minimum
            # the chatbot improved
            if average_validation_loss_error <= min(list_validation_loss_error):
                print('I speak better now')
                early_stopping_check = 0
                saver = tf.train.Saver()
                saver.save(session, checkpoint)
            else:
                print('I do not speak better, pracice more!')
                early_stopping_check += 1
                if early_stopping_check == early_stopping_index:
                    break
    if early_stopping_check == early_stopping_index:
        print('Training Stopped due to early stopper')
        break
    
print('Game Over')



