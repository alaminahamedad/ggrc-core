
# Copyright (C) 2013 Google Inc., authors, and contributors <see AUTHORS file>
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
# Created By: dan@reciprocitylabs.com
# Maintained By: dan@reciprocitylabs.com

from ggrc.models.reflection import AttributeInfo
from . import Record


class RecordBuilder(object):
  def __init__(self, tgt_class):
    self._fulltext_attrs = AttributeInfo.gather_attrs(
        tgt_class, '_fulltext_attrs')

  @staticmethod
  def _compound_getattr(obj, attr):
    """compound_getattr(assessment, 'contact.name') == assessment.contact.name

    None will be returned also if assessment.contact is None.
    """
    for attr_part in attr.split('.'):
      obj = getattr(obj, attr_part, None)
    return obj

  def as_record(self, obj):
    # Defaults. These work when the record is not a custom attribute
    properties = dict([(attr, self._compound_getattr(obj, attr))
                       for attr in self._fulltext_attrs])
    record_id = obj.id
    record_type = obj.__class__.__name__

    # Override defaults to index custom attribute values as attributes of the
    # parent object (the CustomAttributable).
    if "CustomAttributeValue" == record_type:
      record_id = obj.attributable_id
      record_type = obj.attributable_type
      # The name of the attribute property needs to be unique for each object,
      # the value comes from the custom_attribute_value
      properties = {"attribute_value_" + str(obj.id): obj.attribute_value}
    return Record(
        # This logic saves custom attribute values as attributes of the object
        # that owns the attribute values. When obj is not a
        # CustomAttributeValue the values are saved directly.
        record_id,
        record_type,
        obj.context_id,
        '',  # FIXME get any qualifying fields to help in search partitioning
        **properties
    )


def model_is_indexed(tgt_class):
  fulltext_attrs = AttributeInfo.gather_attrs(tgt_class, '_fulltext_attrs')
  return len(fulltext_attrs) > 0


def get_record_builder(obj, builders={}):
  builder = builders.get(obj.__class__.__name__)
  if builder is None:
    builder = RecordBuilder(obj.__class__)
    builders[obj.__class__.__name__] = builder
  return builder


def fts_record_for(obj):
  builder = get_record_builder(obj)
  return builder.as_record(obj)
