# Copyright (C) 2016 Google Inc., authors, and contributors <see AUTHORS file>
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
# Created By: aleh_rymasheuski@epam.com
# Maintained By: aleh_rymasheuski@epam.com

"""
Test RecordBuilder logic
"""

# pylint: disable=protected-access

import unittest

import mock

from ggrc.fulltext.recordbuilder import RecordBuilder


class TestRecordBuilder(unittest.TestCase):
  """Unit tests suite for RecordBuilder class"""

  def test_compound_getattr(self):
    """Test _compound_getattr parsing and application"""
    obj = mock.MagicMock()
    self.assertEqual(obj.foo,
                     RecordBuilder._compound_getattr(obj, 'foo'))
    self.assertEqual(obj.foo.bar,
                     RecordBuilder._compound_getattr(obj, 'foo.bar'))
    self.assertEqual(obj.foo.bar.baz,
                     RecordBuilder._compound_getattr(obj, 'foo.bar.baz'))

    obj.none = None
    self.assertIsNone(RecordBuilder._compound_getattr(obj, 'none'))
    self.assertIsNone(RecordBuilder._compound_getattr(obj, 'none.whatever'))

  @mock.patch('ggrc.fulltext.recordbuilder.Record')
  def test_as_record(self, record_mock):
    """Test fulltext index record generation from object"""
    obj_mock = mock.MagicMock(name='obj')
    class_mock = mock.MagicMock(name='class', __bases__=[])
    class_mock._fulltext_attrs = ['one_field', 'another_field',
                                  'compound_field.sub']

    builder = RecordBuilder(class_mock)
    result = builder.as_record(obj_mock)

    record_mock.assert_called_once_with(
        obj_mock.id,
        obj_mock.__class__.__name__,
        obj_mock.context_id,
        '',  # hardcoded empty parameter in recordbuilder.py
        **{
            'one_field': obj_mock.one_field,
            'another_field': obj_mock.another_field,
            'compound_field.sub': obj_mock.compound_field.sub,
        }
    )
    self.assertEqual(record_mock(), result)
