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
    var initialHash = window.location.hash;

    self.linkScroll = true;

    self.win
      .off("hashchange.panelsolverDocs")
      .one("hashchange.panelsolverDocs", function () {
        self.linkScroll = false;
      });

    window.setTimeout(function () {
      if (window.location.hash === initialHash) {
        self.linkScroll = false;
        self.win.off("hashchange.panelsolverDocs");
      }
    }, 0);
  };
}());
