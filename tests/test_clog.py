# -*- coding: utf-8 -*-
# Copyright 2015 Yelp Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from datetime import date, timedelta
import gzip
import logging
import os
import shutil
import tempfile

import mock
import pytest
import staticconf.testing

from clog.handlers import CLogHandler, DEFAULT_FORMAT
from clog.handlers import get_scribed_logger
from clog.loggers import GZipFileLogger, MockLogger, StdoutLogger
from clog.utils import scribify


first_line = 'First Line.'
second_line = 'Second Line.'
complete_line = '%s\n%s\n' % (first_line, second_line)


class TestGZipFileLogger(object):

    @pytest.yield_fixture(autouse=True)
    def setup_log_dir(self):
        self.log_dir = tempfile.mkdtemp()
        with staticconf.testing.MockConfiguration(
            log_dir=self.log_dir, namespace='clog',
        ):
            yield
        shutil.rmtree(self.log_dir)

    def _open_and_remove(self, filename):
        gz_fh = gzip.open(filename)
        content = gz_fh.read()
        gz_fh.close()
        os.remove(filename)
        return content.decode('utf8')

    def test_no_day(self):
        logger = GZipFileLogger()
        stream = 'first'
        logger.log_line(stream, first_line)
        logger.log_line(stream, second_line)
        logger.close()

        log_filename = GZipFileLogger.get_filename(stream)
        content = self._open_and_remove(log_filename)
        assert content == complete_line

    def test_single_day(self):
        stream = 'second'
        day = date.today()
        logger = GZipFileLogger(day=day)
        logger.log_line(stream, first_line)
        logger.log_line(stream, second_line)
        logger.close()

        log_filename = GZipFileLogger.get_filename(stream, day=day)
        content = self._open_and_remove(log_filename)
        assert content == complete_line

    def test_multi_day(self):
        stream = 'multi'
        first_day = date.today()
        second_day = date.today() + timedelta(days=1)

        for day in (first_day, second_day):
            logger = GZipFileLogger(day=day)
            logger.log_line(stream, first_line)
            logger.log_line(stream, second_line)
            logger.close()

        for day in (first_day, second_day):
            log_filename = GZipFileLogger.get_filename(stream, day=day)
            content = self._open_and_remove(log_filename)
            assert content == complete_line


class MyError(Exception):
    pass


class CLogTestBase(object):
    SIMPLE_FORMAT="%(message)s"
    STREAM_NAME='unit_test'

    @pytest.fixture(autouse=True)
    def _create_logger(self):
        self.logger = MockLogger()
        self.handler = CLogHandler(stream=self.STREAM_NAME, logger=self.logger)
        self.handler.setFormatter(logging.Formatter(self.SIMPLE_FORMAT))
        self.log_instance = logging.getLogger(self.STREAM_NAME)
        self.log_instance.handlers = [self.handler]


class CLogHandlerTest(CLogTestBase):

    def test_handler_preserves_exceptions(self):
        """Test exception preservation a la 18848"""
        # set the default formatter
        self.log_instance.handlers[0].setFormatter(logging.Formatter(DEFAULT_FORMAT))
        try:
            raise MyError("foobar")
        except MyError:
            self.log_instance.exception("example log message")
        assert 1 == len([message for message in self.logger.list_lines(self.STREAM_NAME) if "example log message" in message])


class MiscellaneousCLogMethodsTest(CLogTestBase):
    def test_get_scribed_logger(self):
        log = get_scribed_logger("unit_test_scribed", logging.INFO, fmt=self.SIMPLE_FORMAT, clogger_object=self.logger)
        log.info("This is a test")
        assert "This is a test" in self.logger.list_lines("unit_test_scribed")
        self.logger.clear_lines("unit_test_scribed")
        # test that we don"t double-add
        log = get_scribed_logger("unit_test_scribed", logging.INFO, fmt=self.SIMPLE_FORMAT, clogger_object=self.logger)
        log.info("This is a test")
        assert 1 == len([message for message in self.logger.list_lines("unit_test_scribed") if message == "This is a test"])

    def test_scribify(self):
        assert scribify("this is a test") == "this_is_a_test"
        assert scribify("this\0is a-test\n\n") == "this_is_a-test__"
        assert scribify(u'int\xe9rna\xe7ionalization') == 'int_rna_ionalization'


class TestStdoutLogger(object):

    def test_log_line_and_close(self):
        with mock.patch('sys.stdout') as mock_stdout:
            logger = StdoutLogger()
            logger.log_line('stream1', first_line)
            logger.log_line('stream1', second_line)
            logger.close()

        mock_stdout.write.assert_has_calls([
            mock.call('stream1:{0}\n'.format(first_line)),
            mock.call('stream1:{0}\n'.format(second_line))
        ])
        assert mock_stdout.flush.call_count == 1
