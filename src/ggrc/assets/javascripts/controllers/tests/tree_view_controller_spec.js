/*!
 Copyright (C) 2016 Google Inc., authors, and contributors <see AUTHORS file>
 Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
 Created By: peter@reciprocitylabs.com
 Maintained By: peter@reciprocitylabs.com
 */

describe('CMS.Controllers.TreeView', function () {
  'use strict';

  var Ctrl;  // the controller under test

  beforeAll(function () {
    Ctrl = CMS.Controllers.TreeView;
  });

  describe('init() method', function () {
    var ctrlInst;  // fake controller instance
    var dfdSingleton;
    var method;
    var options;
    var $element;

    beforeEach(function () {
      options = {};
      $element = $('<div></div>');

      ctrlInst = {
        element: $element,
        widget_hidden: jasmine.createSpy('widget_hidden'),
        widget_shown: jasmine.createSpy('widget_shown'),
        options: new can.Map(options)
      };

      method = Ctrl.prototype.init.bind(ctrlInst);

      dfdSingleton = new can.Deferred();
      spyOn(
        CMS.Models.DisplayPrefs, 'getSingleton'
      ).and.returnValue(dfdSingleton);
    });

    // test cases here...
  });

  describe('_build_request_params() method', function () {
    var ctrlInst;  // fake controller instance
    var method;

    beforeEach(function () {
      ctrlInst = {
        options: new can.Map({
          paging: {
            current: 1,
            total: null,
            page_size: 10,
            count: 6
          }
        })
      };

      method = Ctrl.prototype._build_request_params.bind(ctrlInst);
    });

    it('return default params for paging request', function () {
      var expected = {
        page: 1,
        page_size: 10,
        search_value: undefined
      };
      var result = method();

      expect(result.page).toEqual(expected.page);
      expect(result.page_size).toEqual(expected.page_size);
    });

    it('return params for paging request', function () {
      var expected = {
        page: 5,
        page_size: 25,
        search_value: undefined
      };
      var result;

      ctrlInst.options.paging.attr('current', 5);
      ctrlInst.options.paging.attr('total', 150);
      ctrlInst.options.paging.attr('page_size', 25);

      result = method();

      expect(result.page).toEqual(expected.page);
      expect(result.page_size).toEqual(expected.page_size);
      expect(result.current).toEqual(expected.current);
    });
  });

  describe('save_paging_info() method', function () {
    var ctrlInst;  // fake controller instance
    var method;

    beforeAll(function () {
      GGRC.page_object = {
        paging: {
          Assessments: {
            count: 20,
            total: 160
          }
        }
      };

      ctrlInst = {
        options: new can.Map({
          model: {
            shortName: 'Assessments'
          },
          paging: {
            count: null,
            total: null
          }
        })
      };

      method = Ctrl.prototype.save_paging_info.bind(ctrlInst);
    });

    it('check save_paging_info()', function () {
      method();
      expect(ctrlInst.options.paging.count).toEqual(20);
      expect(ctrlInst.options.paging.total).toEqual(160);
    });
  });

  describe('refresh_page() method', function () {
    var ctrlInst;  // fake controller instance
    var method;
    var $element;

    beforeEach(function () {
      $element =
        $('<div><div class="cms_controllers_tree_view_node"></div></div>');

      ctrlInst = {
        element: $element,
        _build_request_params: jasmine.createSpy('_build_request_params'),
        save_paging_info: jasmine.createSpy('save_paging_info'),
        enqueue_items: jasmine.createSpy('enqueue_items'),
        options: new can.Map({
          model: {
            findAll: null
          }
        })
      };

      method = Ctrl.prototype.refresh_page.bind(ctrlInst);
    });

    it('refresh_page()', function () {
      spyOn(ctrlInst.options.model, "findAll")
        .and.returnValue(new $.Deferred().resolve([]));

      method();
      expect(ctrlInst.enqueue_items).toHaveBeenCalled();
    });
  });
});
