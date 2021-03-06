import collections

import numpy as np

from neupy import surgery, algorithms, layers
from neupy.utils import as_tuple

from base import BaseTestCase


class ConnectionIsolationTestCase(BaseTestCase):
    def test_isolate_wrong_data_type(self):
        surgery.isolate_connection_if_needed(layers.Sigmoid(10))

        connection = layers.Input(5) > layers.Sigmoid(10)
        surgery.isolate_connection_if_needed(connection)

        with self.assertRaises(TypeError):
            surgery.isolate_connection_if_needed('invalid object')

    def test_isolate_connection_and_layer(self):
        input_connection = layers.Input(1) > layers.Sigmoid(2)
        output_layer = layers.Sigmoid(3)
        output_connection = input_connection > output_layer

        self.assertEqual(len(output_connection), 3)

        # Test isolation for multiple layers
        self.assertIs(input_connection.output_layer.relate_to_layer,
                      output_layer)
        self.assertFalse(surgery.is_connection_isolated(input_connection))

        surgery.isolate_connection(input_connection)

        self.assertIsNot(input_connection.output_layer.relate_to_layer,
                         output_layer)
        self.assertTrue(surgery.is_connection_isolated(input_connection))

        # Test single layer isolation
        self.assertIs(output_layer.relate_from_layer,
                      input_connection.output_layer)
        self.assertFalse(surgery.is_layer_isolated(output_layer))

        surgery.isolate_layer(output_layer)
        self.assertIsNot(output_layer.relate_from_layer,
                         input_connection.output_layer)
        self.assertTrue(surgery.is_layer_isolated(output_layer))


class SurgeryCutTestCase(BaseTestCase):
    def setUp(self):
        super(SurgeryCutTestCase, self).setUp()
        self.network = algorithms.GradientDescent([
            layers.Input(30),
            layers.Sigmoid(10),
            layers.Sigmoid(20),
            layers.Sigmoid(1),
        ])

    def test_cutting_exceptions(self):
        with self.assertRaises(ValueError):
            surgery.cut(algorithms.PNN(), 0, 1)

        with self.assertRaises(ValueError):
            surgery.cut(self.network, 0, 10)

        with self.assertRaises(ValueError):
            surgery.cut(self.network, 0, 0)

    def test_cut_layers_basics(self):
        testcases = [
            dict(kwargs=dict(connection=self.network, start=0, end=2),
                 expected_sizes=(30, 10)),
            dict(kwargs=dict(connection=self.network, start=1, end=3),
                 expected_sizes=(10, 20)),
            dict(kwargs=dict(connection=self.network, start=1, end=-1),
                 expected_sizes=(10, 20)),
        ]

        for testcase in testcases:
            layers = surgery.cut(**testcase['kwargs'])
            output_shapes = [layer.output_shape for layer in iter(layers)]
            self.assertEqual(
                as_tuple(*output_shapes),
                testcase['expected_sizes']
            )

    def test_cut_one_layer(self):
        input_layer = surgery.cut(self.network, start=0, end=1)
        self.assertIsInstance(input_layer, layers.Input)
        self.assertEqual(input_layer.output_shape, (30,))

    def test_cut_layer_copy(self):
        # Check connection instead of networks as a different
        # acceptible object type.
        connection = self.network.connection
        layer = surgery.cut(connection, start=1, end=2)

        self.assertIsNot(self.network.layers[1], layer)

        x = np.random.random((10, 30))
        y = np.random.random((10, 1))
        self.network.train(x, y, epochs=20)

        trained_layer = self.network.layers[1]
        trained_weight = trained_layer.weight.get_value()
        copied_weight = layer.weight.get_value()

        self.assertTrue(np.any(trained_weight != copied_weight))


class SurgerySewTogetherTestCase(BaseTestCase):
    def test_sew_together_cutted_pieces(self):
        network1 = algorithms.GradientDescent([
            layers.Input(100),
            layers.Sigmoid(200),
            layers.Sigmoid(100),
        ])
        network2 = algorithms.GradientDescent([
            layers.Input(10),
            layers.Sigmoid(20),
            layers.Sigmoid(10),
        ])

        first_part = surgery.cut(network1, start=0, end=2)
        self.assertEqual(first_part.output_shape, (200,))
        self.assertEqual(first_part.input_shape, (100,))

        second_part = surgery.cut(network2, start=0, end=2)
        self.assertEqual(second_part.output_shape, (20,))
        self.assertEqual(second_part.input_shape, (10,))


    def test_sew_together_basic(self):
        connection = surgery.sew_together([
            layers.Sigmoid(24),
            layers.Sigmoid(12) > layers.Sigmoid(6),
            layers.Sigmoid(3),
        ])
        expected_shapes = (24, 12, 6, 3)
        output_shapes = [layer.output_shape for layer in iter(connection)]

        self.assertEqual(as_tuple(*output_shapes), expected_shapes)

    def test_sew_together_when_cutted_piece_already_in_use(self):
        autoencoder = algorithms.Momentum([
            layers.Input(25),
            layers.Sigmoid(15),
            layers.Sigmoid(25),
        ])

        encoder = surgery.cut(autoencoder, start=0, end=2)
        self.assertEqual(len(encoder), 2)

        classifier = algorithms.Momentum(encoder > layers.Softmax(10))

        network = algorithms.GradientDescent([
            layers.Input(5),

            surgery.CutLine(),  # <- first cut point

            layers.Sigmoid(10),
            layers.Sigmoid(20),
            layers.Sigmoid(30),

            surgery.CutLine(),  # <- second cut point

            layers.Sigmoid(1),
        ])
        _, hidden_layers, _ = surgery.cut_along_lines(network)
        self.assertEqual(len(hidden_layers), 3)

        connected_layers = surgery.sew_together([
            encoder,
            layers.Relu(5),
            hidden_layers
        ])
        self.assertEqual(len(connected_layers), 6)

    def test_sew_together_empty_list(self):
        self.assertIs(surgery.sew_together([]), None)


class SurgeryCutAlongLinesTestCase(BaseTestCase):
    def test_cut_along_lines_basic(self):
        network = algorithms.GradientDescent([
            layers.Input(5),

            surgery.CutLine(),

            layers.Sigmoid(10),
            layers.Sigmoid(20),
            layers.Sigmoid(30),

            surgery.CutLine(),

            layers.Sigmoid(1),
        ])

        for connection in (network, network.connection):
            _, interested_layers, _ = surgery.cut_along_lines(connection)
            cutted_shapes = [layer.output_shape for layer in interested_layers]

            self.assertEqual(as_tuple(*cutted_shapes), (10, 20, 30))

    def test_cut_along_lines_check_cut_points(self):
        testcases = (
            dict(
                network=algorithms.GradientDescent([
                    layers.Input(5),
                    layers.Sigmoid(10),
                    layers.Sigmoid(20),
                    layers.Sigmoid(30),

                    surgery.CutLine(),

                    layers.Sigmoid(1),
                ]),
                expected_shapes=[(5, 10, 20, 30), (1,)]
            ),
            dict(
                network=algorithms.GradientDescent([
                    layers.Input(5),
                    layers.Sigmoid(10),
                    layers.Sigmoid(20),
                    layers.Sigmoid(30),

                    surgery.CutLine(),
                    surgery.CutLine(),

                    layers.Sigmoid(1),
                ]),
                expected_shapes=[(5, 10, 20, 30), (1,)]
            ),
            dict(
                network=algorithms.GradientDescent([
                    layers.Input(5),

                    surgery.CutLine(),
                    layers.Sigmoid(10),

                    surgery.CutLine(),
                    layers.Sigmoid(20),

                    surgery.CutLine(),
                    layers.Sigmoid(30),

                    surgery.CutLine(),

                    layers.Sigmoid(1),
                    surgery.CutLine(),
                ]),
                expected_shapes=[(5,), (10,), (20,), (30,), (1,)]
            ),
            dict(
                network=surgery.sew_together([
                    layers.Input(5),
                    layers.Sigmoid(10),
                    layers.Sigmoid(20),
                    layers.Sigmoid(30),
                    layers.Sigmoid(1),
                ]),
                expected_shapes=[(5, 10, 20, 30, 1)]
            ),
            dict(
                network=surgery.sew_together([
                    surgery.CutLine(),
                    layers.Input(5),
                    layers.Sigmoid(10),
                    layers.Sigmoid(20),
                    layers.Sigmoid(30),
                    layers.Sigmoid(1),
                    surgery.CutLine(),
                ]),
                expected_shapes=[(5, 10, 20, 30, 1)]
            ),
        )

        for test_id, testcase in enumerate(testcases):
            connections = surgery.cut_along_lines(testcase['network'])

            actual_shapes = []
            for connection in connections:
                if isinstance(connection, collections.Iterable):
                    shapes = [layer.output_shape for layer in connection]
                else:
                    layer = connection
                    shapes = as_tuple(layer.output_shape)

                actual_shapes.append(as_tuple(*shapes))

            self.assertEqual(
                actual_shapes,
                testcase['expected_shapes'],
                msg="Test ID: {}".format(test_id)
            )
