/*!
 Copyright (C) 2015 Google Inc., authors, and contributors <see AUTHORS file>
 Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
 Created By: brad@reciprocitylabs.com
 Maintained By: miha@reciprocitylabs.com
 */

can.Control("GGRC.Controllers.TreeFilter", {

}, {

  init : function() {
    var parent_control;
    this._super && this._super.apply(this, arguments);
    this.options.states = new can.Observe();
    parent_control = this.element.closest('.cms_controllers_dashboard_widgets')
        .find(".cms_controllers_tree_view").control();
    parent_control && parent_control.options.attr("states", this.options.states);
    this.on();
  }

  , toggle_indicator: function(current_filter){
      var is_expression =
            !!current_filter &&
            !!current_filter.expression.op &&
            current_filter.expression.op.name != "text_search" &&
            current_filter.expression.op.name != "exclude_text_search";

      this.element.find('.filter-input').toggleClass("expression", is_expression);
      this.element.find('.filter-input span i')
        .toggleClass("fa-check-circle green", is_expression);
      this.element.find('.filter-input span i')
        .toggleClass("fa-check-circle-o", !is_expression);
  },
  apply_filter_without_request : function(filter_string){
      var current_filter = GGRC.query_parser.parse(filter_string),
          parent_control = this.element.closest('.cms_controllers_dashboard_widgets')
            .find(".cms_controllers_tree_view").control();

      this.toggle_indicator(current_filter);
      parent_control.options.attr('sort_function', current_filter.order_by.compare);
      parent_control.options.attr('filter', current_filter);
      parent_control.reload_list();
  },
  apply_filter_via_request: function (filter) {
    var parent = this.element.closest('.cms_controllers_dashboard_widgets')
      .find(".cms_controllers_tree_view").control();

    parent.options.paging.attr('filter', filter);
    parent.options.paging.attr('current', 1);
    parent.find();
  },
  apply_filter : function () {
    var value = this.element.find("input[type=text]")[0].value;
    if (GGRC.page_instance().type === 'Audit') {
      this.apply_filter_via_request(value);
    } else {
      this.apply_filter_without_request(value);
    }
  },
  "input[type=reset] click": function (el, ev) {
    this.element.find("input[type=text]")[0].value = "";
    this.apply_filter();
  },
  "input[type=submit] click": function (el, ev) {
    this.apply_filter();
  },
  "input keyup" : function(el, ev) {
    this.toggle_indicator(GGRC.query_parser.parse(el.val()));
    if (ev.keyCode == 13){
      this.apply_filter();
    }
    ev.stopPropagation();
  },
  "input, select change" : function(el, ev) {

    // this is left from the old filters and should eventually be replaced
    // Convert '.' to '__' ('.' will cause can.Observe to try to update a path instead of just a key)
    var name = el.attr("name").replace(/\./g, '__');
    if(el.is(".hasDatepicker")) {
      this.options.states.attr(name, moment(el.val(), "MM/DD/YYYY"));
    } else if (el.is(":checkbox") && !el.is(":checked")) {
      this.options.states.removeAttr(name);
    } else {
      this.options.states.attr(name, el.val());
    }
    ev.stopPropagation();
  }

  , "input[data-lookup] focus" : function(el, ev) {
    this.autocomplete(el);
  }

  , autocomplete : function(el) {
    $.cms_autocomplete.call(this, el);
  }

  , autocomplete_select : function(el, event, ui) {
    setTimeout(function(){
      if (ui.item.title) {
        el.val(ui.item.title, ui.item);
      } else {
        el.val(ui.item.name ? ui.item.name : ui.item.email, ui.item);
      }
      el.trigger('change');
    }, 0);
  }

  , "{states} change" : function(states) {
    var that = this;
    this.element
    .closest(".tree-structure")
    .children(":has(> [data-model],:data(model))").each(function(i, el) {
      var model = $(el).children("[data-model],:data(model)").data("model");
      if(can.reduce(Object.keys(states._data), function(st, key) {
        var val = states[key]
        , test = that.resolve_object(model, key.replace(/__/g, '.'));

       if(val && val.isAfter) {
          if(!test || moment(test).isBefore(val)) {
            return false;
          } else {
            return st;
          }
        } else if (val === "[empty]" && test === "") {
          return st;
        } else if(val && (!test || !~test.toUpperCase().indexOf(val.toUpperCase()))) {
          return false;
        } else {
          return st;
        }
      }, true)) {
        $(el).show();
      } else {
        $(el).hide();
      }
    });
  }

  , '[data-toggle="filter-reset"] click' : function(el, ev) {
    var that = this,
        filter_reset_target = 'input, select',
        checked;

    this.element.find(filter_reset_target).each(function(i, elem) {
      var $elem = $(elem)
      ;

      that.options.states.removeAttr($elem.attr("name").replace(/\./g, '__'));
    });

    if (el.is(':checkbox')) {
      checked = el.prop('checked');
      // Manually reset the form
      el.closest('form')[0].reset();
      if (el.is(":checkbox")) {
        // But not the checkbox
        el.prop('checked', checked);
      }
    }
    can.trigger(this.options.states, "change", "*");
  }

  , resolve_object : function(obj, path) {
    path = path.split(".");
    can.each(path, function(prop) {
      // If the name is blank, use email
      if (prop === 'name' && obj.attr && (!obj.attr(prop) || !obj.attr(prop).trim()) && obj.attr('email') && obj.attr('email').trim()) {
        prop = 'email';
      }
      if (obj.instance) {
        obj = obj.instance;
      }
      obj = obj.attr ? obj.attr(prop) : obj.prop;
      obj = obj && obj.reify ? obj.reify() : obj;
      return obj != null; //stop iterating in case of null/undefined.
    });
    return obj;
  }


});
