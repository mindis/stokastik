import numpy as np
import math
from collections import defaultdict
from sklearn import datasets, linear_model
from sklearn.preprocessing import normalize, scale
from sklearn.metrics import f1_score, accuracy_score
from sklearn.model_selection import KFold
import pickle


def standardize_mean_var(mydata, mean=None, var=None):

    if mean is None and var is None:
        mean = np.mean(mydata, axis=0)
        var = np.var(mydata, axis=0)

    std_data = (mydata - mean) * (var + 1e-5) ** -0.5

    return std_data, mean, var


def one_hot_encoding(classes):
    num_classes = len(set(classes))
    targets = np.array([classes]).reshape(-1)

    return np.eye(num_classes)[targets]


def generate_batches(trainX, trainY, batch_size):
    concatenated = np.column_stack((trainX, trainY))
    np.random.shuffle(concatenated)

    trainX = concatenated[:,:trainX.shape[1]]
    trainY = concatenated[:,trainX.shape[1]:]

    num_batches = math.ceil(float(trainX.shape[0])/batch_size)

    return np.array_split(trainX, num_batches), np.array_split(trainY, num_batches)


def hidden_layer_activation_sigmoid(inputs):
    return (1.0 + np.exp(-inputs))**-1.0


def hidden_layer_activation_relu(inputs):
    return np.maximum(0.1 * inputs, 0.9 * inputs)


def output_layer_activation_class_softmax(inputs):
    inputs = (inputs.T - np.mean(inputs, axis=1)).T

    out = np.exp(inputs)

    return (out.T/np.sum(out, axis=1)).T


def output_layer_grad_class_softmax(pred_outs, true_outs):
    return pred_outs - true_outs


def output_layer_activation_reg(inputs):
    return inputs


def output_layer_grad_reg(pred_outs, true_outs):
    return pred_outs - true_outs


def hidden_layer_grad_sigmoid(inputs):
    return inputs * (1 - inputs)


def hidden_layer_grad_relu(inputs):
    temp = inputs

    temp[temp <= 0.0] = 0.1
    temp[temp > 0.0] = 0.9

    return temp


def loss_cross_entropy(preds, actuals):
    return np.sum(np.sum(-actuals * np.log2(preds), axis=0)) / preds.shape[0]


def loss_mse(preds, actuals):
    return np.sum(np.sum(0.5 * (preds - actuals) ** 2, axis=0)) / preds.shape[0]


def loss_class(outputs, targets):
    num_layers = len(outputs)

    predictions = outputs[num_layers - 1]
    total_loss = loss_cross_entropy(predictions, targets)

    return total_loss


def loss_reg(outputs, targets):
    num_layers = len(outputs)

    predictions = outputs[num_layers - 1]
    total_loss = loss_mse(predictions, targets)

    return total_loss


def train_forward_pass(trainX, weights, biases, gamma, beta, dropout_rate, type):

    outputs, linear_inp, scaled_linear_inp = dict(), dict(), dict()

    mean_linear_inp, var_linear_inp = dict(), dict()

    curr_input = trainX

    for layer in range(len(weights)):
        linear_inp[layer] = curr_input.dot(weights[layer]) + biases[layer]

        scaled_linear_inp[layer], mean_linear_inp[layer], var_linear_inp[layer] = standardize_mean_var(
            linear_inp[layer])

        shifted_inp = gamma[layer] * scaled_linear_inp[layer] + beta[layer]

        if layer == len(weights) - 1:
            if type == "classification":
                outputs[layer] = output_layer_activation_class_softmax(shifted_inp)
            else:
                outputs[layer] = output_layer_activation_reg(shifted_inp)
        else:
            binomial_mat = np.zeros(shape=(trainX.shape[0], weights[layer].shape[1]))

            for row in range(trainX.shape[0]):
                binomial_mat[row,] = np.random.binomial(1, 1 - dropout_rate, weights[layer].shape[1])

            outputs[layer] = hidden_layer_activation_relu(shifted_inp) * binomial_mat

        curr_input = outputs[layer]

    return outputs, linear_inp, scaled_linear_inp, mean_linear_inp, var_linear_inp


def test_forward_pass(testX, weights, biases, gamma, beta, mean_linear_inp, var_linear_inp, type):

    outputs = dict()

    curr_input = testX

    for layer in range(len(weights)):
        linear_inp = curr_input.dot(weights[layer]) + biases[layer]

        scaled_linear_inp, _, _ = standardize_mean_var(linear_inp, mean=mean_linear_inp[layer],
                                                       var=var_linear_inp[layer])

        shifted_inp = gamma[layer] * scaled_linear_inp + beta[layer]

        if layer == len(weights) - 1:
            if type == "classification":
                outputs[layer] = output_layer_activation_class_softmax(shifted_inp)
            else:
                outputs[layer] = output_layer_activation_reg(shifted_inp)
        else:
            outputs[layer] = hidden_layer_activation_relu(shifted_inp)

        curr_input = outputs[layer]

    return outputs


def error_backpropagation(trainX, trainY,
                          outputs,
                          linear_inp, scaled_linear_inp,
                          mean_linear_inp, var_linear_inp,
                          weights, biases, momentums, gamma, beta,
                          bn_learning_rate, weights_learning_rate, momentum_rate,
                          type):

    bp_grads_1, bp_grads_2 = dict(), dict()

    inverse_num_examples = float(1.0) / trainX.shape[0]

    for layer in reversed(range(len(weights))):

        denom = (var_linear_inp[layer] + 1e-5) ** -0.5
        numer = linear_inp[layer] - mean_linear_inp[layer]

        if layer == len(weights) - 1:
            if type == "classification":
                bp_grads_2[layer] = output_layer_grad_class_softmax(outputs[layer], trainY)
            else:
                bp_grads_2[layer] = output_layer_grad_reg(outputs[layer], trainY)
        else:
            bp_grads_2[layer] = hidden_layer_grad_relu(outputs[layer])

            next_layer_weights = weights[layer + 1]

            bp_grads_2[layer] *= bp_grads_1[layer + 1].dot(next_layer_weights.T)

        a = bp_grads_2[layer] * gamma[layer]

        b = np.sum(a * (-0.5 * (denom ** 3.0)) * numer, axis=0)

        c = np.sum(-a * denom, axis=0) + b * np.sum(-2.0 * numer) * inverse_num_examples

        bp_grads_1[layer] = a * denom + b * 2.0 * numer * inverse_num_examples + c * inverse_num_examples

        if layer > 0:
            total_err = outputs[layer - 1].T.dot(bp_grads_1[layer])
        else:
            total_err = trainX.T.dot(bp_grads_1[layer])

        beta[layer] -= bn_learning_rate * np.sum(bp_grads_2[layer], axis=0) * inverse_num_examples

        gamma[layer] -= bn_learning_rate * np.sum(bp_grads_2[layer] * scaled_linear_inp[layer],
                                                    axis=0) * inverse_num_examples

        momentums[layer] = momentum_rate * momentums[layer] - weights_learning_rate * total_err * inverse_num_examples
        weights[layer] += momentums[layer]

        biases[layer] -= weights_learning_rate * np.sum(bp_grads_1[layer], axis=0) * inverse_num_examples

    return weights, biases, momentums, gamma, beta


def initialize(layers, num_features):
    weights, biases, momentums, gamma, beta = dict(), dict(), dict(), dict(), dict()

    for layer in range(len(layers)):
        if layer == 0:
            num_rows = num_features
            num_cols = layers[layer]
        else:
            num_rows = layers[layer - 1]
            num_cols = layers[layer]

        fan_in = num_rows

        if layer < len(layers)-1:
            fan_out = layers[layer + 1]
        else:
            fan_out = fan_in

        r = 4.0 * math.sqrt(float(6.0) / (fan_in + fan_out))

        weights[layer] = np.random.uniform(-r, r, num_rows * num_cols).reshape(num_rows, num_cols)
        momentums[layer] = np.zeros((num_rows, num_cols))
        biases[layer] = np.zeros(num_cols)

        gamma[layer] = np.ones(num_cols)
        beta[layer] = np.zeros(num_cols)

    return weights, biases, momentums, gamma, beta


def scale_weights_dropout(weights, biases, dropout_rate):

    scaled_weights, scaled_biases = dict(), dict()

    for layer in weights:
        scaled_weights[layer] = weights[layer] * (1 - dropout_rate)
        scaled_biases[layer] = biases[layer] * (1 - dropout_rate)

    return scaled_weights, scaled_biases


def train_neural_network(trainX, trainY,
                         hidden_layers,
                         num_epochs=10,
                         weights_learning_rate=0.5,
                         bn_learning_rate=0.5,
                         train_batch_size=32,
                         momentum_rate=0.9,
                         dropout_rate=0.2,
                         ini_weights=None,
                         ini_biases=None,
                         ini_momentums=None,
                         ini_gamma=None,
                         ini_beta=None,
                         type="classification"):

    if type == "classification":
        trainY = one_hot_encoding(trainY)
    else:
        trainY = np.array(trainY).reshape(len(trainY), -1)

    layers = hidden_layers + [trainY.shape[1]]

    if ini_weights is None:
        weights, biases, momentums, gamma, beta = initialize(layers, trainX.shape[1])
    else:
        weights, biases, momentums, gamma, beta = ini_weights, ini_biases, ini_momentums, ini_gamma, ini_beta

    trainX_batches, trainY_batches = generate_batches(trainX, trainY, train_batch_size)

    losses = []

    expected_mean_linear_inp, expected_var_linear_inp = dict(), dict()
    exp_mean_linear_inp, exp_var_linear_inp = dict(), dict()

    for epoch in range(num_epochs):

        for layer in range(len(layers)):
            expected_mean_linear_inp[layer] = np.zeros(weights[layer].shape[1])
            expected_var_linear_inp[layer] = np.zeros(weights[layer].shape[1])

        for batch in range(len(trainX_batches)):

            trainX_batch = trainX_batches[batch]
            trainY_batch = trainY_batches[batch]

            fwd_pass_data = train_forward_pass(trainX_batch, weights, biases, gamma, beta, dropout_rate, type)

            outputs, linear_inp, scaled_linear_inp, mean_linear_inp, var_linear_inp = fwd_pass_data

            for layer in range(len(layers)):
                expected_mean_linear_inp[layer] += mean_linear_inp[layer]
                expected_var_linear_inp[layer] += var_linear_inp[layer]

            backprop = error_backpropagation(trainX_batch, trainY_batch,
                                             outputs=outputs,
                                             linear_inp=linear_inp,
                                             scaled_linear_inp=scaled_linear_inp,
                                             mean_linear_inp=mean_linear_inp,
                                             var_linear_inp=var_linear_inp,
                                             weights=weights,
                                             biases=biases,
                                             momentums=momentums,
                                             gamma=gamma,
                                             beta=beta,
                                             bn_learning_rate=bn_learning_rate,
                                             weights_learning_rate=weights_learning_rate,
                                             momentum_rate=momentum_rate,
                                             type=type)

            weights, biases, momentums, gamma, beta = backprop

        m = train_batch_size

        for layer in range(len(layers)):
            exp_mean_linear_inp[layer] = expected_mean_linear_inp[layer] / len(trainX_batches)

            if m > 1:
                exp_var_linear_inp[layer] = (float(m) / (m-1)) * expected_var_linear_inp[layer] / len(trainX_batches)
            else:
                exp_var_linear_inp[layer] = expected_var_linear_inp[layer] / len(trainX_batches)

        dummy_weights, dummy_biases = scale_weights_dropout(weights, biases, dropout_rate)

        outputs = test_forward_pass(trainX,
                                    weights=dummy_weights,
                                    biases=dummy_biases,
                                    gamma=gamma,
                                    beta=beta,
                                    mean_linear_inp=exp_mean_linear_inp,
                                    var_linear_inp=exp_var_linear_inp,
                                    type=type)

        if type == "classification":
            curr_loss = loss_class(outputs, trainY)
        else:
            curr_loss = loss_reg(outputs, trainY)

        cond = len(losses) > 1 and curr_loss > losses[-1] > losses[-2]

        if cond:
            weights_learning_rate /= float(2.0)

        losses.append(curr_loss)

    weights, biases = scale_weights_dropout(weights, biases, dropout_rate)

    model = (weights, biases, momentums, gamma, beta, exp_mean_linear_inp, exp_var_linear_inp)

    return model


def train_autoencoder(trainX, hidden_layers, num_epochs,
                      weights_learning_rate, bn_learning_rate, momentum_rate, dropout_rate,
                      ini_weights, ini_biases, ini_momentums, ini_gamma, ini_beta):

    layers = hidden_layers

    weights, biases, momentums, gamma, beta = ini_weights, ini_biases, ini_momentums, ini_gamma, ini_beta

    exp_mean_linear_inp, exp_var_linear_inp = dict(), dict()

    curr_input = trainX

    for layer in range(len(hidden_layers)):

        l_weights, l_biases, l_momentums, l_gamma, l_beta = initialize([layers[layer], curr_input.shape[1]],
                                                                       curr_input.shape[1])

        l_weights[0], l_biases[0], l_momentums[0], l_gamma[0], l_beta[0] = ini_weights[layer], ini_biases[layer], \
                                                                           ini_momentums[layer], ini_gamma[layer], \
                                                                           ini_beta[layer]

        model = train_neural_network(curr_input, curr_input,
                                     hidden_layers=[layers[layer]],
                                     num_epochs=num_epochs,
                                     weights_learning_rate=weights_learning_rate,
                                     bn_learning_rate=bn_learning_rate,
                                     train_batch_size=trainX.shape[0],
                                     momentum_rate=momentum_rate,
                                     dropout_rate=dropout_rate,
                                     ini_weights=l_weights,
                                     ini_biases=l_biases,
                                     ini_momentums=l_momentums,
                                     ini_gamma=l_gamma,
                                     ini_beta=l_beta,
                                     type="regression")

        m_weights, m_biases, m_momentums, m_gamma, m_beta, m_exp_mean_linear_inp, m_exp_var_linear_inp = model

        weights[layer], biases[layer], momentums[layer], gamma[layer], beta[layer] = m_weights[0], m_biases[0], \
                                                                                     m_momentums[0], m_gamma[0], m_beta[
                                                                                         0]

        exp_mean_linear_inp[layer], exp_var_linear_inp[layer] = m_exp_mean_linear_inp[0], m_exp_var_linear_inp[0]

        outputs = test_forward_pass(curr_input,
                                    weights=m_weights,
                                    biases=m_biases,
                                    gamma=m_gamma,
                                    beta=m_beta,
                                    mean_linear_inp=m_exp_mean_linear_inp,
                                    var_linear_inp=m_exp_var_linear_inp,
                                    type="regression")

        curr_input = outputs[0]

    return weights, biases, momentums, gamma, beta, exp_mean_linear_inp, exp_var_linear_inp, curr_input


def train_autoencoder_reg(trainX, trainY,
                          hidden_layers,
                          num_epochs=100,
                          weights_learning_rate=0.1,
                          train_batch_size=32,
                          bn_learning_rate=0.5,
                          momentum_rate=0.9,
                          dropout_rate=0.2,
                          ini_weights=None,
                          ini_biases=None,
                          ini_momentums=None,
                          ini_gamma=None,
                          ini_beta=None,
                          type="classification"):

    if type == "classification":
        layers = hidden_layers + [len(set(trainY))]
    else:
        layers = hidden_layers + [1]

    if ini_weights is None:
        weights, biases, momentums, gamma, beta = initialize(layers, trainX.shape[1])
    else:
        weights, biases, momentums, gamma, beta = ini_weights, ini_biases, ini_momentums, ini_gamma, ini_beta

    autoencoder = train_autoencoder(trainX,
                                    hidden_layers=hidden_layers,
                                    num_epochs=num_epochs,
                                    weights_learning_rate=weights_learning_rate,
                                    bn_learning_rate=bn_learning_rate,
                                    momentum_rate=momentum_rate,
                                    dropout_rate=dropout_rate,
                                    ini_weights=weights,
                                    ini_biases=biases,
                                    ini_momentums=momentums,
                                    ini_gamma=gamma,
                                    ini_beta=beta)

    m_weights, m_biases, m_momentums, m_gamma, m_beta, m_exp_mean_linear_inp, m_exp_var_linear_inp, _ = autoencoder

    for layer in range(len(m_weights)):
        weights[layer] = m_weights[layer]
        biases[layer] = m_biases[layer]
        momentums[layer] = m_momentums[layer]
        gamma[layer] = m_gamma[layer]
        beta[layer] = m_beta[layer]

    model = train_neural_network(trainX, trainY,
                                 hidden_layers=hidden_layers,
                                 num_epochs=num_epochs,
                                 weights_learning_rate=weights_learning_rate,
                                 bn_learning_rate=bn_learning_rate,
                                 train_batch_size=train_batch_size,
                                 momentum_rate=momentum_rate,
                                 dropout_rate=dropout_rate,
                                 ini_weights=weights,
                                 ini_biases=biases,
                                 ini_momentums=momentums,
                                 ini_gamma=gamma,
                                 ini_beta=beta,
                                 type=type)

    return model


def predict_neural_network(testX, model, type="classification"):

    weights, biases, _, gamma, beta, exp_mean_linear_inp, exp_var_linear_inp = model

    num_layers = len(weights)

    outputs = test_forward_pass(testX,
                                weights=weights,
                                biases=biases,
                                gamma=gamma,
                                beta=beta,
                                mean_linear_inp=exp_mean_linear_inp,
                                var_linear_inp=exp_var_linear_inp,
                                type=type)

    preds = outputs[num_layers - 1]
    outs = []

    for row in range(preds.shape[0]):
        if type == "classification":
            outs += [np.argmax(preds[row,])]
        else:
            outs += [preds[row,]]

    return outs


def train_nn_cv(trainX, trainY,
                hidden_layers,
                num_epochs=100,
                weights_learning_rate=0.1,
                bn_learning_rate=0.5,
                train_batch_size=32,
                momentum_rate=0.9,
                dropout_rate=0.2,
                num_cv=5,
                ini_weights=None,
                ini_biases=None,
                ini_momentums=None,
                ini_gamma=None,
                ini_beta=None):

    kf = KFold(n_splits=num_cv)

    for train_index, test_index in kf.split(trainX):

        trainX_batch, testX_batch = trainX[train_index], trainX[test_index]
        trainY_batch, testY_batch = trainY[train_index], trainY[test_index]

        model = train_neural_network(trainX_batch, trainY_batch,
                                     hidden_layers=hidden_layers,
                                     weights_learning_rate=weights_learning_rate,
                                     bn_learning_rate=bn_learning_rate,
                                     num_epochs=num_epochs,
                                     train_batch_size=train_batch_size,
                                     momentum_rate=momentum_rate,
                                     dropout_rate=dropout_rate,
                                     ini_weights=ini_weights,
                                     ini_biases=ini_biases,
                                     ini_momentums=ini_momentums,
                                     ini_gamma=ini_gamma,
                                     ini_beta=ini_beta,
                                     type="classification")

        preds_train = predict_neural_network(trainX_batch, model, type="classification")
        preds_test = predict_neural_network(testX_batch, model, type="classification")

        print "Train F1-Score = ", f1_score(trainY_batch, preds_train, average='weighted')
        print "Train Accuracy = ", accuracy_score(trainY_batch, preds_train)

        print "Validation F1-Score = ", f1_score(testY_batch, preds_test, average='weighted')
        print "Validation Accuracy = ", accuracy_score(testY_batch, preds_test)

        print ""