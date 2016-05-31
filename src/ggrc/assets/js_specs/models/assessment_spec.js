/*!
 Copyright (C) 2016 Google Inc., authors, and contributors <see AUTHORS file>
 Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
 Created By: Egor_Miasnikov@epam.com
 Maintained By: Egor_Miasnikov@epam.com
 */

describe('can.Model.Assessment', function () {
  'use strict';

  var Assessment;

  beforeAll(function () {
    Assessment = CMS.Models.Assessment;
  });

  describe('_generate_pagination_request_params() method', function () {
    it('returns the object with params for request', function () {
      var result;
      var origin = {
        page: 2,
        page_size: 10
      };
      var expected = {
        __page: 2,
        __page_size: 10,
        __sort: 'title,description_inline,name,email',
        __sort_desc: false
      };

      result = Assessment._generate_pagination_request_params(origin);
      expect(result).toEqual(expected);
    });

    it('returns default params if it gets empty object', function () {
      var result;
      var origin = {};

      var expected = {
        __page: 1,
        __page_size: 10,
        __sort: 'title,description_inline,name,email',
        __sort_desc: false
      };

      result = Assessment._generate_pagination_request_params(origin);
      expect(result).toEqual(expected);
    });
  });

  describe('findAll() method', function () {
    beforeAll(function () {
      spyOn(GGRC, 'page_instance').and.returnValue({
        type: "Person"
      });
    });

    it("makes a call on backend with specific url", function () {
      spyOn($, 'ajax').and.callFake(function (req) {
        var deffered = $.Deferred();
        expect(req.url).toEqual('/api/assessments');
        expect(req.data).toEqual({});
        deffered.resolve({});
        return deffered.promise();
      });

      Assessment.findAll({});
    });
    it("makes a call on backend with specific url if we're on Audit",
      function () {
        spyOn($, 'ajax').and.callFake(function (req) {
          var deffered = $.Deferred();
          expect(req.url).toEqual('/api/assessments');
          expect(req.data).toEqual({id__in: '1,2,3'});
          deffered.resolve({});
          return deffered.promise();
        });

        Assessment.findAll({id__in: '1,2,3'});
      });

    describe('for Audit page', function () {
      beforeAll(function () {
        GGRC.page_instance = function () {
          return {
            type: "Audit",
            selfLink: "/api/audits/1"
          };
        };
      });
      it("makes a call on backend with specific url if we're on Audit",
        function () {
          spyOn($, 'ajax').and.callFake(function (req) {
            var deffered = $.Deferred();
            expect(req.url).toEqual('/api/audits/1/assessments');
            expect(req.data).toEqual({
              __page: 1,
              __page_size: 10,
              __sort: 'title,description_inline,name,email',
              __sort_desc: false
            });
            deffered.resolve({});
            return deffered.promise();
          });

          Assessment.findAll({});
        });

      it("makes a call on backend with specific url if we're on Audit",
        function () {
          spyOn($, 'ajax').and.callFake(function (req) {
            var deffered = $.Deferred();
            expect(req.url).toEqual('/api/audits/1/assessments');
            expect(req.data).toEqual({
              __page: 3,
              __page_size: 10,
              __sort: 'title,description_inline,name,email',
              __sort_desc: false
            });

            deffered.resolve({});
            return deffered.promise();
          });

          Assessment.findAll({page: 3});
        });

      it("makes a call on backend with specific url if we're on Audit",
        function () {
          spyOn($, 'ajax').and.callFake(function (req) {
            var deffered = $.Deferred();
            expect(req.url).toEqual('/api/audits/1/assessments');
            expect(req.data).toEqual({
              __page: 10,
              __page_size: 10,
              __search: 'verified',
              __sort: 'status',
              __sort_desc: true
            });
            deffered.resolve({});
            return deffered.promise();
          });

          Assessment.findAll({
            page: 10,
            page_size: 10,
            search_value: 'verified',
            sort_by: 'status',
            sort_desc: true
          });
        });
    });
  });
});
