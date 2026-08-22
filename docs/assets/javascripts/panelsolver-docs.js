(function () {
  "use strict";

  var nav =
    window.SphinxRtdTheme &&
    window.SphinxRtdTheme.Navigation;
  if (!nav) {
    return;
  }

  nav.hashChange = function () {
    var self = this;
    self.linkScroll = true;
    self.win.one("hashchange", function () {
      self.linkScroll = false;
    });
  };
}());
