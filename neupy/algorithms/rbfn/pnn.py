import numpy as np

from neupy.utils import format_data, NotTrainedException
from neupy.core.properties import BoundedProperty
from neupy.network.base import BaseNetwork
from neupy.network.learning import LazyLearningMixin
from neupy.algorithms.gd.base import MinibatchTrainingMixin

from .utils import pdf_between_data


__all__ = ('PNN',)


class PNN(BaseNetwork, LazyLearningMixin, MinibatchTrainingMixin):
    """
    Probabilistic Neural Network (PNN). Network applies only to
    the classification problems.

    Notes
    -----
    {LazyLearningMixin.Notes}

    Parameters
    ----------
    std : float
        Standard deviation for the PDF function. Default to ``0.1``.
    {MinibatchTrainingMixin.batch_size}
    {BaseNetwork.verbose}

    Methods
    -------
    {LazyLearningMixin.train}
    {BaseSkeleton.predict}
    predict_proba(input_data)
        Predict probabilities for each class.
    {BaseSkeleton.fit}

    Examples
    --------
    >>> import numpy as np
    >>>
    >>> from sklearn import datasets
    >>> from sklearn import metrics
    >>> from sklearn.cross_validation import train_test_split
    >>> from neupy import algorithms, environment
    >>>
    >>> environment.reproducible()
    >>>
    >>> dataset = datasets.load_digits()
    >>> x_train, x_test, y_train, y_test = train_test_split(
    ...     dataset.data, dataset.target, train_size=0.7
    ... )
    >>>
    >>> nw = algorithms.PNN(std=10, verbose=False)
    >>> nw.train(x_train, y_train)
    >>> result = nw.predict(x_test)
    >>> metrics.accuracy_score(y_test, result)
    0.98888888888888893
    """
    std = BoundedProperty(default=0.1, minval=0)

    def __init__(self, **options):
        super(PNN, self).__init__(**options)
        self.classes = None

    def train(self, input_train, target_train, copy=True):
        """
        Trains network. PNN doesn't actually train, it just stores
        input data and use it for prediction.

        Parameters
        ----------
        input_train : array-like (n_samples, n_features)
        target_train : array-like (n_samples,)
        copy : bool
            If value equal to ``True`` than input matrices will
            be copied. Defaults to ``True``.

        Raises
        ------
        ValueError
            In case if something is wrong with input data.
        """
        input_train = format_data(input_train, copy=copy)
        target_train = format_data(target_train, copy=copy)

        LazyLearningMixin.train(self, input_train, target_train)

        if target_train.shape[1] != 1:
            raise ValueError("Target value should be a vector or a "
                             "matrix with one column")

        classes = self.classes = np.unique(target_train)
        n_classes = classes.size
        n_samples = input_train.shape[0]

        row_comb_matrix = self.row_comb_matrix = np.zeros(
            (n_classes, n_samples)
        )
        class_ratios = self.class_ratios = np.zeros(n_classes)

        for i, class_name in enumerate(classes):
            class_val_positions = (target_train == i)
            row_comb_matrix[i, class_val_positions.ravel()] = 1
            class_ratios[i] = np.sum(class_val_positions)

    def predict_proba(self, input_data):
        """
        Predict probabilities for each class.

        Parameters
        ----------
        input_data : array-like (n_samples, n_features)

        Returns
        -------
        array-like (n_samples, n_classes)
        """
        outputs = self.apply_batches(
            function=self.predict_raw,
            input_data=format_data(input_data),

            description='Prediction batches',
            show_progressbar=True,
            show_error_output=False,
        )
        raw_output = np.concatenate(outputs, axis=1)

        total_output_sum = raw_output.sum(axis=0).reshape((-1, 1))
        return raw_output.T / total_output_sum

    def predict_raw(self, input_data):
        """
        Raw prediction.

        Parameters
        ----------
        input_data : array-like (n_samples, n_features)

        Raises
        ------
        NotTrainedException
            If network hasn't been trained.
        ValueError
            In case if something is wrong with input data.

        Returns
        -------
        array-like (n_samples, n_classes)
        """
        if self.classes is None:
            raise NotTrainedException("Cannot make a prediction. Network "
                                      "haven't been trained")

        super(PNN, self).predict(input_data)

        input_data_size = input_data.shape[1]
        train_data_size = self.input_train.shape[1]

        if input_data_size != train_data_size:
            raise ValueError("Input data must contain {0} features, got "
                             "{1}".format(train_data_size, input_data_size))

        class_ratios = self.class_ratios.reshape((-1, 1))
        pdf_outputs = pdf_between_data(self.input_train, input_data, self.std)

        return np.dot(self.row_comb_matrix, pdf_outputs) / class_ratios

    def predict(self, input_data):
        """
        Predicts class from the input data.

        Parameters
        ----------
        input_data : array-like (n_samples, n_features)

        Returns
        -------
        array-like (n_samples,)
        """
        outputs = self.apply_batches(
            function=self.predict_raw,
            input_data=format_data(input_data),

            description='Prediction batches',
            show_progressbar=True,
            show_error_output=False,
        )
        raw_output = np.concatenate(outputs, axis=1)
        return self.classes[raw_output.argmax(axis=0)]
