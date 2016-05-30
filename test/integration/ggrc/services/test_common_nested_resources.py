# Copyright (C) 2016 Google Inc., authors, and contributors <see AUTHORS file>
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
# Created By: aleh_rymasheuski@epam.com
# Maintained By: aleh_rymasheuski@epam.com

"""
Test REST API calls for nested resources
"""

from ggrc import app
from ggrc import db
from ggrc.models.mixins import Base
from ggrc.services.common import Resource
from integration.ggrc import TestCase
from integration.ggrc.generator import ObjectGenerator
from integration.ggrc.services import model_registered


class OuterModel(Base, db.Model):
  __tablename__ = 'outer_model'
  title = db.Column(db.String)

  _publish_attrs = ['modified_by_id', 'title']
  _update_attrs = ['title']
  _fulltext_attrs = ['title']


class InnerModel(Base, db.Model):
  __tablename__ = 'inner_model'
  title = db.Column(db.String)

  _publish_attrs = ['modified_by_id', 'title']
  _update_attrs = ['title']
  _fulltext_attrs = ['title']


def url_mock_collection(model):
  return '/api/{}'.format(model.__tablename__)


def url_mock_resource(model):
  return '/api/{}/{{0}}'.format(model.__tablename__)


class TestNestedResources(TestCase):
  """Test requests to endpoints like '/audits/1/assessments'"""

  managed_models = [OuterModel, InnerModel]

  OBJECT_URL = '/api/{obj_model}/{obj_id}'
  NESTED_OBJECT_URL = '{}/{{inner_obj_model}}'.format(OBJECT_URL)

  @classmethod
  def setUpClass(cls):
    super(TestNestedResources, cls).setUpClass()
    for model in cls.managed_models:
      Resource.add_to(app.app, url_mock_collection(model), model_class=model)

  def setUp(self):
    super(TestNestedResources, self).setUp()
    for model in self.managed_models:
      model.__table__.create(db.engine, checkfirst=True)

    self.object_generator = ObjectGenerator()
    self.client.get('/login')

  def tearDown(self):
    super(TestNestedResources, self).tearDown()
    # Explicitly destroy test tables
    # Note: This must be after the 'super()', because the session is
    #   closed there.  (And otherwise it might stall due to locks).
    for model in reversed(self.managed_models):
      model.__table__.drop(db.engine, checkfirst=True)
      pass

  @staticmethod
  def mock_model(model_class, **kwargs):
    mock = model_class(**kwargs)
    db.session.add(mock)
    db.session.commit()
    return mock

  @classmethod
  def mock_url(cls, obj, inner_class=None, override=None):
    if override is None:
      override = {}
    parameters = {
      'obj_model': type(obj).__tablename__,
      'obj_id': obj.id,
    }
    if inner_class is None:
      # url for a single object
      url = cls.OBJECT_URL
    else:
      # url for nested objects
      url = cls.NESTED_OBJECT_URL
      parameters['inner_obj_model'] = inner_class.__tablename__

    parameters.update(override)
    return url.format(**parameters)

  @staticmethod
  def parse_response(response, inner_class):
    model_name = inner_class.__tablename__
    collection_name = '{}_collection'.format(model_name)

    collection = response.json[collection_name]
    models = collection[model_name]
    return models, collection

  def test_get(self):
    _, outer = self.object_generator.generate_object(OuterModel)
    _, inner = self.object_generator.generate_object(InnerModel)
    self.object_generator.generate_relationship(outer, inner)

    response = self.client.get(
      self.mock_url(obj=outer, inner_class=InnerModel),
    )

    self.assert200(response)
    models, _ = self.parse_response(response=response, inner_class=InnerModel)

    self.assertEqual(len(models), 1)
    self.assertEqual(models[0]['id'], inner.id)
    self.assertEqual(models[0]['title'], inner.title)

  def test_get_multiple_results(self):
    _, outer = self.object_generator.generate_object(OuterModel)

    inner_objects_count = 5
    ids_titles = []
    for i in range(inner_objects_count):
      _, inner = self.object_generator.generate_object(InnerModel)
      self.object_generator.generate_relationship(outer, inner)
      ids_titles.append((inner.id, inner.title))

    response = self.client.get(
      self.mock_url(obj=outer, inner_class=InnerModel),
    )

    self.assert200(response)
    models, _ = self.parse_response(response=response, inner_class=InnerModel)

    def id_title_key(id_title_tuple):
      return id_title_tuple[0]

    self.assertEqual(len(models), inner_objects_count)
    self.assertListEqual(
      sorted([(model['id'], model['title']) for model in models],
             key=id_title_key),
      sorted(ids_titles,
             key=id_title_key),
    )

  def test_get_no_results(self):
    _, outer = self.object_generator.generate_object(OuterModel)

    response = self.client.get(
      self.mock_url(obj=outer, inner_class=InnerModel),
    )

    self.assert200(response)
    models, _ = self.parse_response(response=response, inner_class=InnerModel)

    self.assertListEqual(models, [])

  def test_get_reverse_relationship(self):
    _, outer = self.object_generator.generate_object(OuterModel)
    _, inner = self.object_generator.generate_object(InnerModel)
    self.object_generator.generate_relationship(outer, inner)

    # "inner" and "outer" are swapped in this test intentionally
    response = self.client.get(
      self.mock_url(obj=inner, inner_class=OuterModel),
    )

    self.assert200(response)
    models, _ = self.parse_response(response=response, inner_class=OuterModel)

    self.assertEqual(len(models), 1)
    self.assertEqual(models[0]['id'], outer.id)
    self.assertEqual(models[0]['title'], outer.title)

  def test_get_bad_accept(self):
    _, outer = self.object_generator.generate_object(OuterModel)
    _, inner = self.object_generator.generate_object(InnerModel)
    self.object_generator.generate_relationship(outer, inner)

    response = self.client.get(
      self.mock_url(obj=outer, inner_class=InnerModel),
      headers={'Accept': 'text/plain'},
    )

    self.assertStatus(response, 406)
    self.assertEqual(response.headers.get('Content-Type'), 'text/plain')
    self.assertEqual(response.data, 'application/json')

  def test_get_invalid_id(self):
    _, outer = self.object_generator.generate_object(OuterModel)
    _, inner = self.object_generator.generate_object(InnerModel)
    self.object_generator.generate_relationship(outer, inner)

    response = self.client.get(
      self.mock_url(obj=outer, inner_class=InnerModel,
                    override={'obj_id': 'text is not acceptable'}),
    )

    self.assert404(response)

  def test_get_missing_id(self):
    _, outer = self.object_generator.generate_object(OuterModel)
    _, inner = self.object_generator.generate_object(InnerModel)
    self.object_generator.generate_relationship(outer, inner)

    response = self.client.get(
      self.mock_url(obj=outer, inner_class=InnerModel,
                    # assume there is no item with this id
                    override={'obj_id': 99999}),
    )

    self.assert404(response)

  def test_get_invalid_inner_class(self):
    class InvalidInnerClassModel(object):
      __tablename__ = 'there_should_be_no_such_model'

    _, outer = self.object_generator.generate_object(OuterModel)

    response = self.client.get(
      self.mock_url(obj=outer,
                    inner_class=InvalidInnerClassModel),
    )

    self.assert404(response)

  def test_get_search(self):
    _, outer = self.object_generator.generate_object(OuterModel)
    _, inner = self.object_generator.generate_object(InnerModel)
    self.object_generator.generate_relationship(outer, inner)

    with model_registered(InnerModel):

      response = self.client.get(
        (self.mock_url(obj=outer,
                       inner_class=InnerModel) +
         '?__search=title={}'.format(inner.title)),
      )

    self.assert200(response)
    models, _ = self.parse_response(response, InnerModel)

    self.assertEqual(len(models), 1)
    self.assertEqual(models[0]['id'], inner.id)
    self.assertEqual(models[0]['title'], inner.title)

  def test_get_sort(self):
    objects = [self.object_generator.generate_object(OuterModel)[1]
               for i in range(10)]
    titles = [obj.title for obj in objects]

    def check_sort_order(sort_parameters, expected_titles):
      response = self.client.get('/api/{model}?{param}'
                                 .format(model=OuterModel.__tablename__,
                                         param=sort_parameters))

      resp_models, _ = self.parse_response(response, OuterModel)
      resp_titles = [obj['title'] for obj in resp_models]

      self.assertListEqual(resp_titles, expected_titles)

    cases = (
      ('__sort=title', sorted(titles)),
      ('__sort=-title', sorted(titles, reverse=True)),
      ('__sort=title&__sort_desc=false', sorted(titles)),
      ('__sort=-title&__sort_desc=false', sorted(titles, reverse=True)),
      ('__sort=title&__sort_desc=true', sorted(titles, reverse=True)),
      ('__sort=-title&__sort_desc=true', sorted(titles)),
    )
    for sort_parameters, expected_titles in cases:
      check_sort_order(sort_parameters, expected_titles)
