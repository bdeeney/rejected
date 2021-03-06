"""Tests for rejected.process"""
import copy
import mock
from pika import channel
from pika import connection
from pika import credentials
from pika import exceptions
import signal
import sys
# Import unittest if 2.7, unittest2 if other version
if (sys.version_info[0], sys.version_info[1]) == (2, 7):
    import unittest
else:
    import unittest2 as unittest

from rejected import consumer
from rejected import process
from rejected import __version__

from . import test_state

class TestImportNamspacedClass(unittest.TestCase):

    def test_import_namespaced_class(self):
        import logging
        (result_class,
         result_version) = process.import_namespaced_class('logging.Logger')
        self.assertEqual(result_class, logging.Logger)

    def test_import_namespaced_class_version(self):
        import logging
        (result_class,
         result_version) = process.import_namespaced_class('logging.Logger')
        self.assertEqual(result_version, logging.__version__)

    def test_import_namespaced_class_no_version(self):
        (result_class,
         result_version) = process.import_namespaced_class('signal.ItimerError')
        self.assertIsNone(result_version)

    def test_import_namespaced_class_failure(self):
        self.assertRaises(ImportError, process.import_namespaced_class,
                          'rejected.fake_module.Classname')


class TestProcess(test_state.TestState):

    config = {'Connections':
                      {'MockConnection':
                               {'host': 'localhost',
                                'port': 5672,
                                'user': 'guest',
                                'pass': 'guest',
                                'vhost': '/'},
                       'MockRemoteConnection':
                               {'host': 'remotehost',
                                'port': 5672,
                                'user': 'guest',
                                'pass': 'guest',
                                'vhost': '/'}
                      },
              'Consumers':
                      {'MockConsumer':
                               {'consumer': 'tests.mocks.MockConsumer',
                                'connections': ['MockConnection'],
                                'config': {'test_value': True,
                                           'num_value': 100},
                                'min': 2,
                                'max': 5,
                                'max_errors': 10,
                                'qos_prefetch': 5,
                                'ack': True,
                                'queue': 'mock_queue'},
                       'MockConsumer2':
                               {'consumer': 'mock_consumer.MockConsumer',
                                'connections': ['MockConnection',
                                                'MockRemoteConnection'],
                                'config': {'num_value': 50},
                                'min': 1,
                                'max': 2,
                                'queue': 'mock_you'}}}
    mock_args = {'config': config,
                 'connection_name': 'MockConnection',
                 'consumer_name': 'MockConsumer',
                 'stats_queue': 'StatsQueue'}

    def setUp(self):
        self._obj = self.new_process()

    def tearDown(self):
        del self._obj

    def new_kwargs(self, kwargs):
        return copy.deepcopy(kwargs)

    def new_counter(self):
        return {process.Process.ERROR: 0,
                process.Process.PROCESSED: 0,
                process.Process.REDELIVERED: 0,
                process.Process.TIME_SPENT: 0,
                process.Process.TIME_WAITED: 0}

    def new_process(self, kwargs=None):
        with mock.patch('multiprocessing.Process'):
            return process.Process(group=None,
                                   name='MockProcess',
                                   kwargs=kwargs or
                                          self.new_kwargs(self.mock_args))

    def new_mock_channel(self):
        return mock.Mock(spec=channel.Channel)

    def new_mock_connection(self):
        return mock.Mock(spec=connection.Connection)

    def new_mock_parameters(self, host, port, vhost, user, password):
        mock_credentials = mock.Mock(spec=credentials.PlainCredentials)
        mock_credentials.username = user
        mock_credentials.password = password
        mock_parameters = mock.Mock(spec=connection.ConnectionParameters)
        mock_parameters.credentials = mock_credentials
        mock_parameters.host = host
        mock_parameters.port = port
        mock_parameters.virtual_host = vhost
        return mock_parameters

    def get_connection_parameters(self, host, port, vhost, user, password):
        with mock.patch('pika.credentials.PlainCredentials'):
            with mock.patch('pika.connection.ConnectionParameters'):
                return self._obj._get_connection_parameters(host,
                                                                port,
                                                                vhost,
                                                                user,
                                                                password)

    def default_connection_parameters(self):
        return {'host': 'rabbitmq',
                'port': 5672,
                'user': 'nose',
                'password': 'mock',
                'vhost': 'unittest'}

    def mock_parameters(self):
        kwargs = self.default_connection_parameters()
        return self.get_connection_parameters(**kwargs)

    def test_app_id(self):
        expectation = 'rejected/%s' % __version__
        self.assertEqual(self._obj._AMQP_APP_ID, expectation)

    def test_counter_data_structure(self):
        self.assertEqual(self._obj._new_counter_dict(), self.new_counter())

    def test_startup_state(self):
        new_process = self.new_process()
        self.assertEqual(new_process._state, process.Process.STATE_INITIALIZING)

    def test_startup_time(self):
        mock_time = 123456789.012345
        with mock.patch('time.time', return_value=mock_time):
            new_process = self.new_process()
            self.assertEqual(new_process._state_start, mock_time)

    def test_startup_counts(self):
        new_process = self.new_process()
        self.assertEqual(new_process._counts, self.new_counter())

    def test_startup_channel_is_none(self):
        new_process = self.new_process()
        self.assertIsNone(new_process._channel)

    def test_startup_consumer_is_none(self):
        new_process = self.new_process()
        self.assertIsNone(new_process._consumer)

    def test_ack_message(self):
        delivery_tag = 'MockDeliveryTag-1'
        mock_ack = mock.Mock()
        self._obj._channel = self.new_mock_channel()
        self._obj._channel.basic_ack = mock_ack
        self._obj._ack_message(delivery_tag)
        mock_ack.assert_called_once_with(delivery_tag=delivery_tag)

    def test_count(self):
        expectation = 10
        self._obj._counts[process.Process.REDELIVERED] = expectation
        self.assertEqual(self._obj._count(process.Process.REDELIVERED),
                                              expectation)

    def test_get_config(self):
        connection = 'MockConnection'
        name = 'MockConsumer'
        number = 5
        pid = 1234
        expectation = {'connection': self.config['Connections'][connection],
                       'connection_name': connection,
                       'consumer_name': name,
                       'name': '%s_%i_tag_%i' % (name, pid, number)}
        with mock.patch('os.getpid', return_value=pid):
            self.assertEqual(self._obj._get_config(self.config, number,
                                                       name, connection),
                             expectation)

    def test_get_connection_parameters_host(self):
        kwargs = self.default_connection_parameters()
        result = self.get_connection_parameters(**kwargs)
        self.assertEqual(result.host, kwargs['host'])

    def test_get_connection_parameters_port(self):
        kwargs = self.default_connection_parameters()
        result = self.get_connection_parameters(**kwargs)
        self.assertEqual(result.port, kwargs['port'])

    def test_get_connection_parameters_vhost(self):
        kwargs = self.default_connection_parameters()
        result = self.get_connection_parameters(**kwargs)
        self.assertEqual(result.virtual_host, kwargs['vhost'])

    def test_get_connection_parameters_user(self):
        kwargs = self.default_connection_parameters()
        result = self.get_connection_parameters(**kwargs)
        self.assertEqual(result.credentials.username, kwargs['user'])

    def test_get_connection_parameters_password(self):
        kwargs = self.default_connection_parameters()
        result = self.get_connection_parameters(**kwargs)
        self.assertEqual(result.credentials.password, kwargs['password'])

    def test_get_connection_called_get_parameters(self):
        config = self.config['Connections']['MockConnection']
        kwargs = {'host': config['host'],
                  'port': config['port'],
                  'user': config['user'],
                  'password': config['pass'],
                  'vhost': config['vhost']}
        parameters = self.get_connection_parameters(**kwargs)
        with mock.patch.object(process.Process, '_get_connection_parameters',
                               return_value=parameters) as mock_method:
            with mock.patch('pika.adapters.tornado_connection.TornadoConnection'):
                new_process = self.new_process()
                new_process._get_connection(self.config['Connections'],
                                            'MockConnection')
                mock_method.assert_called_once_with(config['host'],
                                                    config['port'],
                                                    config['vhost'],
                                                    config['user'],
                                                    config['pass'])

    def test_get_connection_with_exception_raised(self):
        config = self.config['Connections']['MockConnection']
        kwargs = {'host': config['host'],
                  'port': config['port'],
                  'user': config['user'],
                  'password': config['pass'],
                  'vhost': config['vhost']}
        parameters = self.get_connection_parameters(**kwargs)
        with mock.patch.object(process.Process, '_get_connection_parameters',
                               return_value=parameters):
            with mock.patch('pika.adapters.tornado_connection.TornadoConnection',
                            side_effect=exceptions.AMQPConnectionError):
                new_process = self.new_process()
                new_process._get_connection(self.config['Connections'],
                                            'MockConnection')
                self.assertEqual(new_process._state,
                                 process.Process.STATE_STOPPED)

    def test_get_consumer_raises_import_error(self):
        self.assertRaises(ImportError, self._obj._get_consumer,
                          self.config['Consumers']['MockConsumer2'])

    def test_get_consumer_version_output(self):
        config = {'consumer': 'optparse.OptionParser'}
        with mock.patch('logging.Logger.info') as info:
            import optparse
            self._obj._get_consumer(config)
            info.assert_called_with('Creating consumer %s v%s',
                                    config['consumer'],
                                    optparse.__version__)

    def test_get_consumer_no_version_output(self):
        config = {'consumer': 'StringIO.StringIO'}
        with mock.patch('logging.Logger.info') as info:
            self._obj._get_consumer(config)
            info.assert_called_with('Creating consumer %s', config['consumer'])

    @mock.patch.object(consumer.Consumer, '__init__')
    def test_get_consumer_with_config(self, mock_method):
        config = {'consumer': 'rejected.consumer.Consumer',
                  'config': {'field': 'value', 'true': True}}
        new_process = self.new_process()
        new_process._get_consumer(config)
        mock_method.assert_called_once_with(config['config'])

    @mock.patch.object(consumer.Consumer, '__init__', side_effect=ImportError)
    def test_get_consumer_with_config_is_none(self, mock_method):
        config = {'consumer': 'rejected.consumer.Consumer',
                  'config': {'field': 'value', 'true': True}}
        new_process = self.new_process()
        new_process._get_consumer(config)
        self.assertIsNone(new_process._get_consumer(config))

    @mock.patch.object(consumer.Consumer, '__init__')
    def test_get_consumer_with_no_config(self, mock_method):
        config = {'consumer': 'rejected.consumer.Consumer'}
        new_process = self.new_process()
        new_process._get_consumer(config)
        mock_method.assert_called_once_with()

    @mock.patch.object(consumer.Consumer, '__init__', side_effect=ImportError)
    def test_get_consumer_with_no_config_is_none(self, mock_method):
        config = {'consumer': 'rejected.consumer.Consumer'}
        new_process = self.new_process()
        self.assertIsNone(new_process._get_consumer(config))

    def test__process(self):
        mock_consumer = mock.Mock(consumer.Consumer)
        new_process = self.new_process()
        new_process._consumer = mock_consumer
        message = 'Hello World'
        new_process._process(message)
        mock_consumer.process.assert_called_once_with(message)

    def test__process_consumer_exception(self):
        mock_consumer = mock.Mock(consumer.Consumer)
        mock_consumer.process.side_effect = consumer.ConsumerException
        new_process = self.new_process()
        new_process._consumer = mock_consumer
        message = 'Hello World'
        self.assertRaises(consumer.ConsumerException, new_process._process,
                          message)

    def test__process_other_exception(self):
        mock_consumer = mock.Mock(consumer.Consumer)
        mock_consumer.process.side_effect = AttributeError
        new_process = self.new_process()
        new_process._consumer = mock_consumer
        message = 'Hello World'
        self.assertRaises(consumer.ConsumerException, new_process._process,
                          message)

    def test_reject_message(self):
        delivery_tag = 'MockDeliveryTag-1'
        mock_reject = mock.Mock()
        self._obj._channel = self.new_mock_channel()
        self._obj._channel.basic_reject = mock_reject
        self._obj._reject(delivery_tag)
        mock_reject.assert_called_once_with(delivery_tag=delivery_tag)

    def test_set_qos_prefetch_value(self):
        new_process = self.new_process()
        new_process._setup(**self.mock_args)
        mock_channel = self.new_mock_channel()
        new_process._channel = mock_channel
        value = 12
        new_process._set_qos_prefetch(value)
        mock_channel.basic_qos.assert_called_once_with(prefetch_count=value)

    def test_set_qos_prefetch_no_value(self):
        new_process = self.new_process()
        new_process._setup(**self.mock_args)
        mock_channel = self.new_mock_channel()
        new_process._channel = mock_channel
        new_process._set_qos_prefetch()
        value = new_process._qos_prefetch
        mock_channel.basic_qos.assert_called_once_with(prefetch_count=value)

    def test_set_state_idle_to_processing_check_time_waited(self):
        new_process = self.new_process()
        new_process._state = new_process.STATE_IDLE
        new_process._counts[new_process.TIME_WAITED] = 0
        prop_mock = mock.Mock()
        value = 10
        prop_mock.__get__ = mock.Mock(return_value=value)
        with mock.patch.object(process.Process, '_time_in_state', prop_mock):
            new_process._set_state(new_process.STATE_PROCESSING)
            self.assertEqual(new_process._counts[new_process.TIME_WAITED],
                             value)

    def test_set_state_processing_to_idle_check_time_spent(self):
        new_process = self.new_process()
        new_process._state = new_process.STATE_PROCESSING
        new_process._counts[new_process.TIME_SPENT] = 0
        prop_mock = mock.Mock()
        value = 10
        prop_mock.__get__ = mock.Mock(return_value=value)
        with mock.patch.object(process.Process, '_time_in_state', prop_mock):
            new_process._set_state(new_process.STATE_IDLE)
            self.assertEqual(new_process._counts[new_process.TIME_SPENT], value)

    def test_setup_signal_handlers(self):
        signals = {signal.SIGPROF: self._obj.get_stats,
                   signal.SIGABRT: self._obj.stop}
        def side_effect(*args):
            if args[0] not in signals:
                assert False, '%i not in %r' % (args[0], signals)
            assert (args[1] == signals[args[0]]), \
                   'Callback for %i was not %r' % (args[0], args[1])
        with mock.patch('signal.signal', side_effect=side_effect):
            self._obj._setup_signal_handlers()

    def mock_setup(self, new_process=None, side_effect=None):
        with mock.patch('signal.signal', side_effect=side_effect):
            with mock.patch('rejected.process.import_namespaced_class',
                            return_value=(mock.Mock, None)):
                if not new_process:
                    new_process = self.new_process(self.mock_args)
                    new_process._setup(**self.mock_args)
                return new_process

    def test_setup_setup_signal_handlers(self):

        new_process = self.new_process(self.mock_args)
        new_process._setup(**self.mock_args)
        signals = {signal.SIGPROF: new_process.get_stats,
                   signal.SIGABRT: new_process.stop}
        def side_effect(*args):
            if args[0] not in signals:
                assert False, '%i not in %r' % (args[0], signals)
            assert (args[1] == signals[args[0]]),\
                'Callback for %i was not %r' % (args[0], args[1])
        self.mock_setup(new_process, side_effect)

    def test_setup_stats_queue(self):
        mock_process = self.mock_setup()
        self.assertEqual(mock_process._stats_queue,
                         self.mock_args['stats_queue'])

    def test_setup_consumer_name(self):
        mock_process = self.mock_setup()
        self.assertEqual(mock_process._stats_queue,
                         self.mock_args['stats_queue'])

    def test_setup_config(self):
        mock_process = self.mock_setup()
        config = self.config['Consumers']['MockConsumer']
        self.assertEqual(mock_process._config, config)

    def test_setup_with_consumer_config(self):
        new_process = self.new_process()
        new_process._setup(**self.mock_args)
        self.assertEqual(new_process._consumer._configuration,
                         self.config['Consumers']['MockConsumer']['config'])

    def test_setup_config_queue_name(self):
        mock_process = self.mock_setup()
        self.assertEqual(mock_process._queue_name,
                         self.config['Consumers']['MockConsumer']['queue'])

    def test_setup_config_ack(self):
        mock_process = self.mock_setup()
        self.assertEqual(mock_process._ack,
                         self.config['Consumers']['MockConsumer']['ack'])

    def test_setup_max_error_count(self):
        mock_process = self.mock_setup()
        self.assertEqual(mock_process._max_error_count,
                         self.config['Consumers']['MockConsumer']['max_errors'])

    def test_setup_prefetch_count_no_config(self):
        args = copy.deepcopy(self.mock_args)
        del args['config']['Consumers']['MockConsumer']['qos_prefetch']
        mock_process = self.new_process()
        mock_process._setup(**args)
        self.assertEqual(mock_process._base_qos_prefetch,
                         process.Process._QOS_PREFETCH_COUNT)

    def test_setup_prefetch_count_with_config(self):
        mock_process = self.mock_setup()
        self.assertEqual(mock_process._base_qos_prefetch,
                         self.config['Consumers']['MockConsumer']['qos_prefetch'])

    def test_setup_connection_arguments(self):
        with mock.patch.object(process.Process,
                               '_get_connection') as mock_method:
            self.mock_setup()
            mock_method.assert_called_once_with(self.config['Connections'],
                                                'MockConnection')

    def test_setup_connection_value(self):
        mock_connection = mock.Mock()
        with mock.patch.object(process.Process, '_get_connection',
                               return_value=mock_connection):
            mock_process = self.mock_setup()
            self.assertEqual(mock_process._connection, mock_connection)

    def test_is_idle_state_processing(self):
        self._obj._state = self._obj.STATE_PROCESSING
        self.assertFalse(self._obj.is_idle)

    def test_is_running_state_processing(self):
        self._obj._state = self._obj.STATE_PROCESSING
        self.assertTrue(self._obj.is_running)

    def test_is_shutting_down_state_processing(self):
        self._obj._state = self._obj.STATE_PROCESSING
        self.assertFalse(self._obj.is_shutting_down)

    def test_is_stopped_state_processing(self):
        self._obj._state = self._obj.STATE_PROCESSING
        self.assertFalse(self._obj.is_stopped)

    def test_too_many_errors_true(self):
        self._obj._max_error_count = 1
        self._obj._counts[self._obj.ERROR] = 2
        self.assertTrue(self._obj.too_many_errors)

    def test_too_many_errors_false(self):
        self._obj._max_error_count = 5
        self._obj._counts[self._obj.ERROR] = 2
        self.assertFalse(self._obj.too_many_errors)

    def test_state_processing_desc(self):
        self._obj._state = self._obj.STATE_PROCESSING
        self.assertEqual(self._obj.state_description,
                         self._obj._STATES[self._obj.STATE_PROCESSING])
