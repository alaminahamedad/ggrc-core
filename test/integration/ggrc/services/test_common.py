# Copyright (C) 2013 Google Inc., authors, and contributors <see AUTHORS file>
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
# Created By: david@reciprocitylabs.com
# Maintained By: david@reciprocitylabs.com

"""
Test common REST API calls
"""

# Disabling this pylint rule to be able to specify more descriptive test name:
# e.g test_collection_get_pagination_default_page_size. So, that this rule will
# note limit us to 30 chars.
# pylint: disable=invalid-name

import ggrc
import ggrc.builder
import ggrc.services
import json
import time
from datetime import datetime
from ggrc import db
from ggrc.fulltext import get_indexer
from ggrc.fulltext.recordbuilder import fts_record_for
from ggrc.models.mixins import Base
from ggrc.services.common import Resource
from integration.ggrc import TestCase
from integration.ggrc.services import model_registered
from urlparse import urlparse
from wsgiref.handlers import format_date_time
from nose.plugins.skip import SkipTest


class ServicesTestMockModel(Base, ggrc.db.Model):
  __tablename__ = 'test_model'
  foo = db.Column(db.String)
  title = db.Column(db.String)
  code = db.Column(db.String, unique=True)

  # REST properties
  _publish_attrs = ['modified_by_id', 'foo', 'code', 'title']
  _update_attrs = ['foo', 'code', 'title']
  _fulltext_attrs = ['foo', 'title']

  def to_json(self):
    date_format = '%Y-%m-%dT%H:%M:%S'
    updated_at = unicode(self.updated_at.strftime(date_format))
    created_at = unicode(self.created_at.strftime(date_format))
    return {
        u'id': int(self.id),
        u'selfLink': unicode(URL_MOCK_RESOURCE.format(self.id)),
        u'type': unicode(self.__class__.__name__),
        u'modified_by': {
            u'href': u'/api/people/1',
            u'id': self.modified_by_id,
            u'type': 'Person',
            u'context_id': None
        } if self.modified_by_id is not None else None,
        u'modified_by_id': (int(self.modified_by_id)
                            if self.modified_by_id is not None else None),
        u'updated_at': updated_at,
        u'created_at': created_at,
        u'context': {u'id': self.context_id}
        if self.context_id is not None else None,
        u'foo': (unicode(self.foo) if self.foo else None),
        u'title': (unicode(self.title) if self.title else None),
        u'code': (unicode(self.code) if self.code else None),
    }

URL_MOCK_COLLECTION = '/api/mock_resources'
URL_MOCK_RESOURCE = '/api/mock_resources/{0}'
Resource.add_to(
    ggrc.app.app, URL_MOCK_COLLECTION, model_class=ServicesTestMockModel)

COLLECTION_ALLOWED = ['HEAD', 'GET', 'POST', 'OPTIONS']
RESOURCE_ALLOWED = ['HEAD', 'GET', 'PUT', 'DELETE', 'OPTIONS']


class TestResource(TestCase):
  """Resource unit tests suite."""

  def setUp(self):
    super(TestResource, self).setUp()
    # Explicitly create test tables
    if not ServicesTestMockModel.__table__.exists(db.engine):
      ServicesTestMockModel.__table__.create(db.engine)
    with self.client.session_transaction() as session:
      session['permissions'] = {
          "__GGRC_ADMIN__": {"__GGRC_ALL__": {"contexts": [0]}}
      }

  def tearDown(self):
    super(TestResource, self).tearDown()
    # Explicitly destroy test tables
    # Note: This must be after the 'super()', because the session is
    #   closed there.  (And otherwise it might stall due to locks).
    if ServicesTestMockModel.__table__.exists(db.engine):
      ServicesTestMockModel.__table__.drop(db.engine)

  @staticmethod
  def mock_url(resource=None, **parameters):
    """Make a mock url for `resource` with double-underscored `parameters`

    Example:
      url = mock_url(resource='my_class', sort='id', search='test')
      # URL_MOCK_RESOURCE.format(resource) + '?__sort=id&__search=test'
      url = mock_url(page=2, page_size=14, sort='date')
      # URL_MOCK_COLLECTION + '?__page=2&__page_size=14&sort=date'
    """
    if resource is not None:
      return URL_MOCK_RESOURCE.format(resource)

    params = []
    for parameter, value in parameters.iteritems():
      params.append('__{parameter}={value}'.format(parameter=parameter,
                                                   value=value))

    return ('?'.join([URL_MOCK_COLLECTION, '&'.join(params)])
            if params else URL_MOCK_COLLECTION)

  @staticmethod
  def mock_model(**kwargs):
    mock = ServicesTestMockModel(**kwargs)
    ggrc.db.session.add(mock)
    ggrc.db.session.commit()
    return mock

  def mock_models(self, count=1):
    """Mock models of a given count."""
    mocks = []
    mocks_json = []

    for i in xrange(count):
      date = datetime(2013, 4, 1 + i, 0, 0, 0, 0)
      item = self.mock_model(created_at=date, updated_at=date)
      mocks.append(item)
      mocks_json.append(item.to_json())

    return mocks, mocks_json

  @staticmethod
  def http_timestamp(timestamp):
    return format_date_time(time.mktime(timestamp.utctimetuple()))

  @staticmethod
  def get_location(response):
    """Ignore the `http://localhost` prefix of the Location"""
    return response.headers['Location'][16:]

  @staticmethod
  def headers(*args, **kwargs):
    ret = list(args)
    ret.append(('X-Requested-By', 'Unit Tests'))
    ret.extend(kwargs.items())
    return ret

  @staticmethod
  def parse_response(response):
    collection = response.json['test_model_collection']
    models = collection['test_model']
    return models, collection

  def assertRequiredHeaders(self, response, headers=None):
    default_headers = {'Content-Type': 'application/json'}
    if headers is not None:
      default_headers.update(headers)

    self.assertIn('Etag', response.headers)
    self.assertIn('Last-Modified', response.headers)
    self.assertIn('Content-Type', response.headers)
    for k, v in default_headers.items():
      self.assertEqual(v, response.headers.get(k))

  def assertAllow(self, response, allowed=None):
    self.assert405(response)
    self.assertIn('Allow', response.headers)
    if allowed:
      self.assertItemsEqual(allowed, response.headers['Allow'].split(', '))

  def assertOptions(self, response, allowed):
    self.assertIn('Allow', response.headers)
    self.assertItemsEqual(allowed, response.headers['Allow'].split(', '))

  def assertKeysIn(self, keys, data):
    """Assert keys are present in a given dict."""
    for key in keys:
      self.assertIn(key, data)

  def test_x_requested_by_required(self):
    response = self.client.post(self.mock_url())
    self.assert400(response)
    response = self.client.put(self.mock_url() + '/1', data='blah')
    self.assert400(response)
    response = self.client.delete(self.mock_url() + '/1')
    self.assert400(response)

  def test_empty_collection_get(self):
    response = self.client.get(self.mock_url(), headers=self.headers())
    self.assert200(response)

  def test_missing_resource_get(self):
    response = self.client.get(self.mock_url('foo'), headers=self.headers())
    self.assert404(response)

  def test_collection_get(self):
    """Test collection GET method from common.py"""

    # Note: Flask-SQLAlchemy also removes the session instance at the end of
    # every request. Therefore the session is cleared along with any objects
    # added to it every time you call client.get() or another client method
    # In order to get rid of DetachedInstance error we need to generate JSON
    # representation before making a request or re-add the object instance
    # back to the session with db.session.add(mock)
    models, models_json = self.mock_models(count=2)
    last_modified = max(model.updated_at for model in models)

    response = self.client.get(self.mock_url(), headers=self.headers())
    self.assert200(response)
    self.assertRequiredHeaders(
        response=response,
        headers={'Last-Modified': self.http_timestamp(last_modified)},
    )
    resp_models, collection = self.parse_response(response=response)
    self.assertIn('test_model_collection', response.json)
    self.assertEqual(2, len(collection))
    self.assertIn('selfLink', collection)
    self.assertIn('test_model', collection)
    self.assertEqual(2, len(resp_models))
    self.assertDictEqual(models_json[1], resp_models[0])
    self.assertDictEqual(models_json[0], resp_models[1])

  def test_collection_get_pagination(self):
    """Test collection GET method with pagination"""
    self.mock_models(count=4)
    response = self.client.get(self.mock_url(page=1, page_size=2),
                               headers=self.headers())
    resp_models, collection = self.parse_response(response=response)
    self.assertEqual(2, len(resp_models))
    self.assertIn('paging', collection)

    paging = collection['paging']
    self.assertKeysIn(('total', 'count', 'first', 'next', 'last'), paging)
    self.assertEqual(2, paging['count'])
    self.assertEqual(4, paging['total'])

  def test_collection_get_pagination_default_page_size(self):
    """Test collection GET method with pagination (default page size)"""
    self.mock_models(count=30)
    response = self.client.get(self.mock_url(page=1),
                               headers=self.headers())
    resp_models, collection = self.parse_response(response=response)
    self.assertEqual(Resource.DEFAULT_PAGE_SIZE, len(resp_models))
    self.assertIn('paging', collection)

    paging = collection['paging']
    self.assertKeysIn(('total', 'count', 'first', 'next', 'last'), paging)
    self.assertEqual(2, paging['count'])
    self.assertEqual(30, paging['total'])

  def test_collection_get_sorting_single_attr(self):
    """Test collection GET method with sorting of a single attribute"""
    self.mock_models(count=3)
    response = self.client.get(self.mock_url(sort='updated_at'),
                               headers=self.headers())
    resp_models, _ = self.parse_response(response=response)

    expected = ['2013-04-0%sT00:00:00' % (i + 1) for i in range(3)]
    for model, expected in zip(resp_models, expected):
      self.assertEqual(model['updated_at'], expected)

  def test_collection_get_sorting_single_attr_asc(self):
    """Test collection GET method with sorting of a single attribute
    ascending"""
    self.mock_models(count=3)
    response = self.client.get(self.mock_url(sort='updated_at',
                                             sort_desc='false'),
                               headers=self.headers())
    resp_models, _ = self.parse_response(response=response)

    expected = ['2013-04-0%sT00:00:00' % (i + 1) for i in range(3)]
    for model, expected in zip(resp_models, expected):
      self.assertEqual(model['updated_at'], expected)

  def test_collection_get_sorting_single_attr_desc(self):
    """Test collection GET method with sorting of a single attribute
    descending"""
    self.mock_models(count=3)
    response = self.client.get(self.mock_url(sort='updated_at',
                                             sort_desc='true'),
                               headers=self.headers())
    resp_models, _ = self.parse_response(response=response)

    expected = ['2013-04-0%sT00:00:00' % (i + 1) for i in range(3)]
    for model, expected in zip(resp_models, reversed(expected)):
      self.assertEqual(model['updated_at'], expected)

  def test_collection_get_sorting_multiple_attr(self):
    """Test collection GET method with sorting of multiple attributes"""
    # create models twice so we have same updated_at for some models
    self.mock_models(count=3)
    self.mock_models(count=3)

    response = self.client.get(self.mock_url(sort='updated_at,id'))
    resp_models, _ = self.parse_response(response=response)

    for model, expected in zip(resp_models, (('2013-04-01T00:00:00', 1),
                                             ('2013-04-01T00:00:00', 4),
                                             ('2013-04-02T00:00:00', 2),
                                             ('2013-04-02T00:00:00', 5),
                                             ('2013-04-03T00:00:00', 3),
                                             ('2013-04-03T00:00:00', 6))):
      self.assertEqual((model['updated_at'], model['id']), expected)

  def test_collection_get_sorting_multiple_attr_mixed_dir(self):
    """Test collection GET method with sorting of multiple attributes with
    mixed sort direction (ascending/descending)"""
    # create models twice so we have same updated_at for some models
    self.mock_models(count=3)
    self.mock_models(count=3)

    response = self.client.get(self.mock_url(sort='updated_at,-id'))
    resp_models, _ = self.parse_response(response=response)

    for model, expected in zip(resp_models, (('2013-04-01T00:00:00', 4),
                                             ('2013-04-01T00:00:00', 1),
                                             ('2013-04-02T00:00:00', 5),
                                             ('2013-04-02T00:00:00', 2),
                                             ('2013-04-03T00:00:00', 6),
                                             ('2013-04-03T00:00:00', 3))):
      self.assertEqual((model['updated_at'], model['id']), expected)

  def test_collection_get_search(self):
    """Test collection GET method from common.py with __search parameter"""

    def make_mock_index(mock_model, property_list):
      """Add index records for listed properties of mock_model"""
      indexer = get_indexer()
      for prop in property_list:
        index_record = indexer.record_type(
            key=mock_model.id,
            type=mock_model.__class__.__name__,
            property=prop,
            content=getattr(mock_model, prop),
        )
        ggrc.db.session.add(index_record)
      ggrc.db.session.commit()

    mock_model1 = self.mock_model(title='foo')
    mock_model2 = self.mock_model(title='bar')
    make_mock_index(mock_model1, ['title'])
    make_mock_index(mock_model2, ['title'])
    mock1 = mock_model1.to_json()
    mock2 = mock_model2.to_json()

    with model_registered(ServicesTestMockModel):

      resp_models, _ = self.parse_response(self.client.get(
          self.mock_url(search='foo'),
          headers=self.headers(),
      ))
      self.assertListEqual([mock1], resp_models)

      resp_models, _ = self.parse_response(self.client.get(
          self.mock_url(search='baz'),
          headers=self.headers(),
      ))
      self.assertListEqual([], resp_models)

      resp_models, _ = self.parse_response(self.client.get(
          self.mock_url(search='title=foo'),
          headers=self.headers(),
      ))
      self.assertListEqual([mock1], resp_models)

      resp_models, _ = self.parse_response(self.client.get(
          self.mock_url(search='title=baz'),
          headers=self.headers(),
      ))
      self.assertListEqual([], resp_models)

      resp_models, _ = self.parse_response(self.client.get(
          self.mock_url(search='title!=foo'),
          headers=self.headers(),
      ))
      self.assertListEqual([mock2], resp_models)

      resp_models, _ = self.parse_response(self.client.get(
          self.mock_url(search='title!=baz'),
          headers=self.headers(),
      ))

      def model_key(model):
        return model['id']
      self.assertListEqual(sorted([mock1, mock2], key=model_key),
                           sorted(resp_models, key=model_key))

  def test_collection_get_search_on_real_index(self):
    """Test collection GET method from common.py `__search`ing on real index"""
    mock_model1 = self.mock_model(foo='foo_value_1', title='title_value_1')
    mock_model2 = self.mock_model(foo='foo_value_2', title='title_value_2')
    mock1 = mock_model1.to_json()
    mock2 = mock_model2.to_json()
    indexer = get_indexer()
    indexer.create_record(fts_record_for(mock_model1))
    indexer.create_record(fts_record_for(mock_model2))

    with model_registered(ServicesTestMockModel):

      resp_models, _ = self.parse_response(self.client.get(
          self.mock_url(search='foo=foo_value_1'),
          headers=self.headers(),
      ))
      self.assertListEqual([mock1], resp_models)
      resp_models, _ = self.parse_response(self.client.get(
          self.mock_url(search='title=title_value_1'),
          headers=self.headers(),
      ))
      self.assertListEqual([mock1], resp_models)
      resp_models, _ = self.parse_response(self.client.get(
          self.mock_url(search='foo=foo_value_2'),
          headers=self.headers(),
      ))
      self.assertListEqual([mock2], resp_models)
      resp_models, _ = self.parse_response(self.client.get(
          self.mock_url(search='title=title_value_2'),
          headers=self.headers(),
      ))
      self.assertListEqual([mock2], resp_models)

  def test_resource_get(self):
    """Test resource GET method from common.py"""
    models, models_json = self.mock_models(count=1)
    last_modified = max(model.updated_at for model in models)
    response = self.client.get(self.mock_url(models[0].id),
                               headers=self.headers())
    self.assert200(response)
    self.assertRequiredHeaders(
        response=response,
        headers={'Last-Modified': self.http_timestamp(last_modified)},
    )
    self.assertIn('services_test_mock_model', response.json)
    self.assertDictEqual(models_json[0],
                         response.json['services_test_mock_model'])

  def test_collection_put(self):
    self.assertAllow(
        self.client.put(URL_MOCK_COLLECTION, headers=self.headers()),
        COLLECTION_ALLOWED)

  def test_collection_delete(self):
    self.assertAllow(
        self.client.delete(URL_MOCK_COLLECTION, headers=self.headers()),
        COLLECTION_ALLOWED)

  def test_collection_post_successful(self):
    data = json.dumps(
        {'services_test_mock_model': {'foo': 'bar', 'context': None}})
    response = self.client.post(
        URL_MOCK_COLLECTION,
        content_type='application/json',
        data=data,
        headers=self.headers(),
    )
    self.assertStatus(response, 201)
    self.assertIn('Location', response.headers)
    response = self.client.get(
        self.get_location(response), headers=self.headers())
    self.assert200(response)
    self.assertRequiredHeaders(response)
    self.assertIn('services_test_mock_model', response.json)
    self.assertIn('foo', response.json['services_test_mock_model'])
    self.assertEqual('bar', response.json['services_test_mock_model']['foo'])
    # check the collection, too
    response = self.client.get(URL_MOCK_COLLECTION, headers=self.headers())
    self.assert200(response)
    self.assertEqual(
        1, len(response.json['test_model_collection']['test_model']))
    self.assertEqual(
        'bar', response.json['test_model_collection']['test_model'][0]['foo'])

  def test_collection_post_successful_single_array(self):
    data = json.dumps(
        [{'services_test_mock_model': {'foo': 'bar', 'context': None}}])
    response = self.client.post(
        URL_MOCK_COLLECTION,
        content_type='application/json',
        data=data,
        headers=self.headers(),
    )
    self.assert200(response)
    self.assertEqual(type(response.json), list)
    self.assertEqual(len(response.json), 1)

    response = self.client.get(URL_MOCK_COLLECTION, headers=self.headers())
    self.assert200(response)
    self.assertEqual(
        1, len(response.json['test_model_collection']['test_model']))
    self.assertEqual(
        'bar', response.json['test_model_collection']['test_model'][0]['foo'])

  def test_collection_post_successful_multiple(self):
    data = json.dumps([
        {'services_test_mock_model': {'foo': 'bar1', 'context': None}},
        {'services_test_mock_model': {'foo': 'bar2', 'context': None}},
    ])
    response = self.client.post(
        URL_MOCK_COLLECTION,
        content_type='application/json',
        data=data,
        headers=self.headers(),
    )
    self.assert200(response)
    self.assertEqual(type(response.json), list)
    self.assertEqual(len(response.json), 2)
    self.assertEqual(
        'bar1', response.json[0][1]['services_test_mock_model']['foo'])
    self.assertEqual(
        'bar2', response.json[1][1]['services_test_mock_model']['foo'])
    response = self.client.get(URL_MOCK_COLLECTION, headers=self.headers())
    self.assert200(response)
    self.assertEqual(
        2, len(response.json['test_model_collection']['test_model']))

  def test_collection_post_successful_multiple_with_errors(self):
    data = json.dumps([
        {'services_test_mock_model':
            {'foo': 'bar1', 'code': 'f1', 'context': None}},
        {'services_test_mock_model':
            {'foo': 'bar1', 'code': 'f1', 'context': None}},
        {'services_test_mock_model':
            {'foo': 'bar2', 'code': 'f2', 'context': None}},
        {'services_test_mock_model':
            {'foo': 'bar2', 'code': 'f2', 'context': None}},
    ])
    response = self.client.post(
        URL_MOCK_COLLECTION,
        content_type='application/json',
        data=data,
        headers=self.headers(),
    )

    self.assertEqual(403, response.status_code)
    self.assertEqual([201, 403, 201, 403], [i[0] for i in response.json])
    self.assertEqual(
        'bar1', response.json[0][1]['services_test_mock_model']['foo'])
    self.assertEqual(
        'bar2', response.json[2][1]['services_test_mock_model']['foo'])
    response = self.client.get(URL_MOCK_COLLECTION, headers=self.headers())
    self.assert200(response)
    self.assertEqual(
        2, len(response.json['test_model_collection']['test_model']))

  def test_collection_post_bad_request(self):
    response = self.client.post(
        URL_MOCK_COLLECTION,
        content_type='application/json',
        data='This is most definitely not valid content.',
        headers=self.headers(),
    )
    self.assert400(response)

  def test_collection_post_bad_content_type(self):
    response = self.client.post(
        URL_MOCK_COLLECTION,
        content_type='text/plain',
        data="Doesn't matter, now does it?",
        headers=self.headers(),
    )
    self.assertStatus(response, 415)

  def test_put_successful(self):
    mock = self.mock_model(foo='buzz')
    response = self.client.get(self.mock_url(mock.id), headers=self.headers())
    self.assert200(response)
    self.assertRequiredHeaders(response)
    obj = response.json
    self.assertEqual('buzz', obj['services_test_mock_model']['foo'])
    obj['services_test_mock_model']['foo'] = 'baz'
    url = urlparse(obj['services_test_mock_model']['selfLink']).path
    original_headers = dict(response.headers)
    # wait a moment so that we can be sure to get differing Last-Modified
    # after the put - the lack of latency means it's easy to end up with
    # the same HTTP timestamp thanks to the standard's lack of precision.
    time.sleep(1.1)
    response = self.client.put(
        url,
        data=json.dumps(obj),
        headers=self.headers(
            ('If-Unmodified-Since', original_headers['Last-Modified']),
            ('If-Match', original_headers['Etag']),
        ),
        content_type='application/json',
    )
    self.assert200(response)
    response = self.client.get(url, headers=self.headers())
    self.assert200(response)
    self.assertNotEqual(
        original_headers['Last-Modified'], response.headers['Last-Modified'])
    self.assertNotEqual(
        original_headers['Etag'], response.headers['Etag'])
    self.assertEqual('baz', response.json['services_test_mock_model']['foo'])

  def test_put_bad_request(self):
    mock = self.mock_model(foo='tough')
    response = self.client.get(self.mock_url(mock.id), headers=self.headers())
    self.assert200(response)
    self.assertRequiredHeaders(response)
    url = urlparse(response.json['services_test_mock_model']['selfLink']).path
    response = self.client.put(
        url,
        content_type='application/json',
        data='This is most definitely not valid content.',
        headers=self.headers(
            ('If-Unmodified-Since', response.headers['Last-Modified']),
            ('If-Match', response.headers['Etag']))
    )
    self.assert400(response)

  @SkipTest
  def test_put_and_delete_conflict(self):
    mock = self.mock_model(foo='mudder')
    response = self.client.get(self.mock_url(mock.id), headers=self.headers())
    self.assert200(response)
    self.assertRequiredHeaders(response)
    obj = response.json
    obj['services_test_mock_model']['foo'] = 'rocks'
    mock = ggrc.db.session.query(ServicesTestMockModel).filter(
        ServicesTestMockModel.id == mock.id).one()
    mock.foo = 'dirt'
    ggrc.db.session.add(mock)
    ggrc.db.session.commit()
    url = urlparse(obj['services_test_mock_model']['selfLink']).path
    original_headers = dict(response.headers)
    response = self.client.put(
        url,
        data=json.dumps(obj),
        headers=self.headers(
            ('If-Unmodified-Since', original_headers['Last-Modified']),
            ('If-Match', original_headers['Etag'])
        ),
        content_type='application/json',
    )
    self.assertStatus(response, 409)
    response = self.client.delete(
        url,
        headers=self.headers(
            ('If-Unmodified-Since', original_headers['Last-Modified']),
            ('If-Match', original_headers['Etag'])
        ),
        content_type='application/json',
    )
    self.assertStatus(response, 409)

  @SkipTest
  def test_put_and_delete_missing_precondition(self):
    mock = self.mock_model(foo='tricky')
    response = self.client.get(self.mock_url(mock.id), headers=self.headers())
    self.assert200(response)
    obj = response.json
    obj['services_test_mock_model']['foo'] = 'strings'
    url = urlparse(obj['services_test_mock_model']['selfLink']).path
    response = self.client.put(
        url,
        data=json.dumps(obj),
        content_type='application/json',
        headers=self.headers(),
    )
    self.assertStatus(response, 428)
    response = self.client.delete(url, headers=self.headers())
    self.assertStatus(response, 428)

  @SkipTest
  def test_delete_successful(self):
    mock = self.mock_model(foo='delete me')
    response = self.client.get(self.mock_url(mock.id), headers=self.headers())
    self.assert200(response)
    url = urlparse(response.json['services_test_mock_model']['selfLink']).path
    response = self.client.delete(
        url,
        headers=self.headers(
            ('If-Unmodified-Since', response.headers['Last-Modified']),
            ('If-Match', response.headers['Etag']),
        ),
    )
    self.assert200(response)
    response = self.client.get(url, headers=self.headers())
    # 410 would be nice! But, requires a tombstone.
    self.assert404(response)

  def test_options(self):
    mock = self.mock_model()
    response = self.client.open(
        self.mock_url(mock.id), method='OPTIONS', headers=self.headers())
    self.assertOptions(response, RESOURCE_ALLOWED)

  def test_collection_options(self):
    response = self.client.open(
        self.mock_url(), method='OPTIONS', headers=self.headers())
    self.assertOptions(response, COLLECTION_ALLOWED)

  def test_get_bad_accept(self):
    mock1 = self.mock_model(foo='baz')
    response = self.client.get(
        self.mock_url(mock1.id),
        headers=self.headers(('Accept', 'text/plain')))
    self.assertStatus(response, 406)
    self.assertEqual('text/plain', response.headers.get('Content-Type'))
    self.assertEqual('application/json', response.data)

  def test_collection_get_bad_accept(self):
    response = self.client.get(
        URL_MOCK_COLLECTION,
        headers=self.headers(('Accept', 'text/plain')))
    self.assertStatus(response, 406)
    self.assertEqual('text/plain', response.headers.get('Content-Type'))
    self.assertEqual('application/json', response.data)

  def test_get_if_none_match(self):
    mock1 = self.mock_model(foo='baz')
    response = self.client.get(
        self.mock_url(mock1.id),
        headers=self.headers(('Accept', 'application/json')))
    self.assert200(response)
    previous_headers = dict(response.headers)
    response = self.client.get(
        self.mock_url(mock1.id),
        headers=self.headers(
            ('Accept', 'application/json'),
            ('If-None-Match', previous_headers['Etag']),
        ),
    )
    self.assertStatus(response, 304)
    self.assertIn('Etag', response.headers)

  @SkipTest
  def test_collection_get_if_non_match(self):
    self.mock_model(foo='baz')
    response = self.client.get(
        URL_MOCK_COLLECTION,
        headers=self.headers(('Accept', 'application/json')))
    self.assert200(response)
    previous_headers = dict(response.headers)
    response = self.client.get(
        URL_MOCK_COLLECTION,
        headers=self.headers(
            ('Accept', 'application/json'),
            ('If-None-Match', previous_headers['Etag']),
        ),
    )
    self.assertStatus(response, 304)
    self.assertIn('Etag', response.headers)
