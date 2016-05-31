/*!
    Copyright (C) 2013 Google Inc., authors, and contributors <see AUTHORS file>
    Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
    Created By: brad@reciprocitylabs.com
    Maintained By: brad@reciprocitylabs.com
*/

(function(can, $) {
/*  RefreshQueue
 *
 *  enqueue(obj, force=false) -> queue or null
 *  trigger() -> Deferred
 */

can.Construct("ModelRefreshQueue", {
}, {
    init: function(model) {
      this.model = model;
      this.ids = [];
      this.deferred = new $.Deferred();
      this.triggered = false;
      this.completed = false;
      this.updated_at = Date.now();
    }

  , enqueue: function(id) {
      if (this.triggered) {
        return null;
      }
      if (this.ids.indexOf(id) === -1) {
        this.ids.push(id);
        this.updated_at = Date.now();
      }
      return this;
    }

  , trigger: function () {
      var self = this;
      if (!this.triggered) {
        this.triggered = true;
        if (this.ids.length) {
          this.model.findAll({ id__in: this.ids.join(",") }).then(function () {
            self.completed = true;
            self.deferred.resolve();
          }, function () {
            self.deferred.reject.apply(self.deferred, arguments);
          });
        } else {
          this.completed = true;
          this.deferred.resolve();
        }
      }
      return this.deferred;
    }

  , trigger_with_debounce: function(delay, manager) {
      var ms_to_wait = (delay || 0) + this.updated_at - Date.now();

      if (!this.triggered) {
        if (ms_to_wait < 0 && (!manager || manager.triggered_queues().length < 6)) {
          this.trigger();
        } else {
          setTimeout(this.proxy('trigger_with_debounce', delay, manager), ms_to_wait);
        }
      }

      return this.deferred;
    }
});

can.Construct("RefreshQueueManager", {
    model_bases: {
      // This won't work until Relatable/Documentable/etc mixins can handle
      // queries with multiple `type` values.
      //  Regulation: 'Directive'
      //, Contract: 'Directive'
      //, Policy: 'Directive'
      //, Standard: 'Directive'
      //, System: 'SystemOrProcess'
      //, Process: 'SystemOrProcess'
    }
}, {
    init: function() {
      this.null_queue = new ModelRefreshQueue(null);
      this.queues = [];
    }

  , triggered_queues: function() {
      return can.map(this.queues, function(queue) {
        if (queue.triggered)
          return queue;
      });
    }

  , enqueue: function(obj, force) {
      var self = this
        , model = obj.constructor
        , model_name = model.shortName
        , found_queue = null
        , id = obj.id
        ;

      if (!obj.selfLink) {
        if (obj instanceof can.Model) {
          model_name = obj.constructor.shortName;
        } else if (obj.type) {
          // FIXME: obj.kind is to catch invalid stubs coming from Directives
          model_name = obj.type || obj.kind;
        }
      }
      model = CMS.Models[model_name];

      if (this.constructor.model_bases[model_name]) {
        model_name = this.constructor.model_bases[model_name];
        model = CMS.Models[model_name];
      }

      if (!force)
        // Check if the ID is already contained in another queue
        can.each(this.queues, function(queue) {
          if (!found_queue
              && queue.model === model && queue.ids.indexOf(id) > -1)
            found_queue = queue;
        });

      if (!found_queue) {
        can.each(this.queues, function(queue) {
          var isEnqueue = !found_queue && queue.model === model
            && !queue.triggered;
          var instance = GGRC.page_object;
          /* NOTE
           Temporary solutions for apply pagination on Assessments view.
           We do not use batch loading for Assessment list.
           */
          if (instance && instance.type !== 'Audit' && queue.model &&
            queue.model.shortName !== 'Assessment') {
            isEnqueue = isEnqueue && queue.ids.length < 150;
          }

          if (isEnqueue) {
            found_queue = queue.enqueue(id);
            return false;
          }
        });
        if (!found_queue) {
          found_queue = new ModelRefreshQueue(model);
          this.queues.push(found_queue);
          found_queue.enqueue(id);
          found_queue.deferred.done(function() {
            var index = self.queues.indexOf(found_queue);
            if (index > -1)
              self.queues.splice(index, 1);
          });
        }
      }

      return found_queue;
    }
});

can.Construct("RefreshQueue", {
    refresh_queue_manager: new RefreshQueueManager(),
    refresh_all: function(instance, props, force) {
      var dfd = new $.Deferred();

      _refresh_all(instance, props, dfd);
      return dfd;

      // Helper function called recursively for each property
      function _refresh_all(instance, props, dfd) {
        var prop = props[0],
            next_props = props.slice(1),
            next = instance[prop],
            refresh_queue = new RefreshQueue(),
            dfds = [],
            deferred;

        if (next) {
          refresh_queue.enqueue(next, force);
          deferred = refresh_queue.trigger();
        } else if (instance.get_binding) {
          next = instance.get_binding(prop);
          if (next) {
            deferred = next.refresh_instances(force);
          }
        }
        if (deferred) {
          deferred.then(function(refreshed_items) {
            if (next_props.length) {
              can.each(refreshed_items, function(item) {
                var d = new $.Deferred();
                _refresh_all(item, next_props, d);
                dfds.push(d);
              });
              // Resolve the original deferred only when all list deferreds
              //   have been resolved
              $.when.apply($, dfds).then(function(items) {
                dfd.resolve(items);
              }, function() {
                dfd.reject.apply(this, arguments);
              });
              return;
            }
            // All items were refreshed, resolve the deferred
            if (next.push || next.list) {
              // Last refreshed property was a list
              dfd.resolve(refreshed_items);
            }
            // Last refreshed property was a single instance, return it as such
            dfd.resolve(refreshed_items[0]);
          }, function() {
            dfd.reject.apply(this, arguments);
          });
        } else {
          console.warn("refresh_all failed at", prop);
        }
      }
    },
}, {
    init: function() {
      this.objects = [];
      this.queues = [];
      this.deferred = new $.Deferred();
      this.triggered = false;
      this.completed = false;

      return this;
    }

  , enqueue: function (obj, force) {
      if (!obj) {
        return;
      }
      if (this.triggered) {
        return null;
      }
      if (obj.push) {
        can.each(obj, function (o) {
          this.enqueue(o, force);
        }, this);
        return this;
      }

      this.objects.push(obj);
      if (force || !obj.selfLink) {
        queue = this.constructor.refresh_queue_manager.enqueue(obj, force);
        if (this.queues.indexOf(queue) === -1)
          this.queues.push(queue);
      }
      return this;
    }

  , trigger: function (delay) {
      var self = this
        , deferreds = []
        ;

      if (!delay) {
        delay = 150;
      }

      this.triggered = true;
      can.each(this.queues, function(queue) {
        deferreds.push(queue.trigger_with_debounce(delay, self.constructor.refresh_queue_manager));
      });

      if (deferreds.length) {
        $.when.apply($, deferreds).then(function () {
          self.deferred.resolve(can.map(self.objects, function (obj) {
            return obj.reify();
          }));
        }, function () {
          self.deferred.reject.apply(self.deferred, arguments);
        });
      } else {
        return this.deferred.resolve(this.objects);
      }

      return this.deferred;
    }
});


})(window.can, window.can.$);
