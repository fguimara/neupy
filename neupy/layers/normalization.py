import theano
import theano.tensor as T
import numpy as np

from neupy.core.properties import (NumberProperty, ProperFractionProperty,
                                   ParameterProperty)
from neupy.utils import asfloat, as_tuple
from neupy.core.init import Initializer, Constant
from .activations import AxesProperty
from .utils import dimshuffle
from .base import BaseLayer


__all__ = ('BatchNorm',)


def find_opposite_axes(axes, ndim):
    """
    Based on the total number of dimensions function
    finds all axes that are missed in the specified
    list ``axes``.

    Parameters
    ----------
    axes : list or tuple
        Already known axes.
    ndim : int
        Total number of dimensions

    Returns
    -------
    list

    Examples
    --------
    >>> from neupy.layers.normalization import find_opposite_axes
    >>> find_opposite_axes([0, 1], ndim=4)
    [2, 3]
    >>>
    >>> find_opposite_axes([], ndim=4)
    [0, 1, 2, 3]
    >>>
    >>> find_opposite_axes([0, 1, 2], ndim=3)
    []
    """
    if any(axis >= ndim for axis in axes):
        raise ValueError("Some axes have invalid values. Axis value "
                         "should be between 0 and {}".format(ndim))

    return [axis for axis in range(ndim) if axis not in axes]


class BatchNorm(BaseLayer):
    """
    Batch-normalization layer.

    Parameters
    ----------
    axes : int, tuple with int or None
        The axis or axes along which normalization is applied.
        ``None`` means that normalization will be applied over
        all axes except the first one. In case of 4D tensor it will
        be equal to ``(0, 2, 3)``. Defaults to ``None``.
    epsilon : float
        Epsilon is a positive constant that adds to the standard
        deviation to prevent the division by zero.
        Defaults to ``1e-5``.
    alpha : float
        Coefficient for the exponential moving average of
        batch-wise means and standard deviations computed during
        training; the closer to one, the more it will depend on
        the last batches seen. Value needs to be between ``0`` and ``1``.
        Defaults to ``0.1``.
    gamma : array-like, Theano variable, scalar or Initializer
        Default initialization methods you can
        find :ref:`here <init-methods>`.
        Defaults to ``Constant(value=1)``.
    beta : array-like, Theano variable, scalar or Initializer
        Default initialization methods you can
        find :ref:`here <init-methods>`.
        Defaults to ``Constant(value=0)``.

    Methods
    -------
    {BaseLayer.Methods}

    Attributes
    ----------
    {BaseLayer.Attributes}

    References
    ----------
    .. [1] Batch Normalization: Accelerating Deep Network Training
           by Reducing Internal Covariate Shift,
           http://arxiv.org/pdf/1502.03167v3.pdf
    """
    axes = AxesProperty(default=None)
    alpha = ProperFractionProperty(default=0.1)
    epsilon = NumberProperty(default=1e-5, minval=0)
    gamma = ParameterProperty(default=Constant(value=1))
    beta = ParameterProperty(default=Constant(value=0))

    def initialize(self):
        super(BatchNorm, self).initialize()

        input_shape = as_tuple(None, self.input_shape)
        ndim = len(input_shape)

        if self.axes is None:
            # If ndim == 4 then axes = (0, 2, 3)
            # If ndim == 2 then axes = (0,)
            self.axes = tuple(axis for axis in range(ndim) if axis != 1)

        if any(axis >= ndim for axis in self.axes):
            raise ValueError("Cannot apply batch normalization on the axis "
                             "that doesn't exist.")

        opposite_axes = find_opposite_axes(self.axes, ndim)
        parameter_shape = [input_shape[axis] for axis in opposite_axes]

        if any(parameter is None for parameter in parameter_shape):
            unknown_dim_index = parameter_shape.index(None)
            raise ValueError("Cannot apply batch normalization on the axis "
                             "with unknown size over the dimension #{} "
                             "(0-based indeces).".format(unknown_dim_index))

        self.running_mean = theano.shared(
            name='running_mean_{}'.format(self.layer_id),
            value=asfloat(np.zeros(parameter_shape))
        )
        self.running_inv_std = theano.shared(
            name='running_inv_std_{}'.format(self.layer_id),
            value=asfloat(np.ones(parameter_shape))
        )

        if isinstance(self.gamma, Initializer):
            self.gamma = self.gamma.sample(parameter_shape)

        if isinstance(self.beta, Initializer):
            self.beta = self.beta.sample(parameter_shape)

        self.gamma = theano.shared(
            name='gamma_{}'.format(self.layer_id),
            value=asfloat(self.gamma),
        )
        self.beta = theano.shared(
            name='beta_{}'.format(self.layer_id),
            value=asfloat(self.beta),
        )
        self.parameters = [self.gamma, self.beta]

    def output(self, input_value):
        epsilon = asfloat(self.epsilon)
        alpha = asfloat(self.alpha)
        gamma, beta = self.gamma, self.beta

        ndim = input_value.ndim
        axes = self.axes

        running_mean = self.running_mean
        running_inv_std = self.running_inv_std

        input_mean = input_value.mean(axes)
        input_var = input_value.var(axes)
        input_inv_std = T.inv(T.sqrt(input_var + epsilon))

        self.updates = [(
            running_inv_std,
            asfloat(1 - alpha) * running_inv_std + alpha * input_inv_std
        ), (
            running_mean,
            asfloat(1 - alpha) * running_mean + alpha * input_mean
        )]

        if not self.training_state:
            mean = running_mean
            inv_std = running_inv_std

        else:
            mean = input_mean
            inv_std = input_inv_std

        opposite_axes = find_opposite_axes(axes, ndim)

        beta = dimshuffle(beta, ndim, opposite_axes)
        gamma = dimshuffle(gamma, ndim, opposite_axes)
        mean = dimshuffle(mean, ndim, opposite_axes)
        inv_std = dimshuffle(inv_std, ndim, opposite_axes)

        normalized_value = (input_value - mean) * inv_std
        return gamma * normalized_value + beta
