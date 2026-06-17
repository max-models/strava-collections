(async function () {
  async function init() {
    try {
      const { default: GLightbox } = await import("glightbox");
      try {
        await import("glightbox/dist/css/glightbox.css");
      } catch (cssErr) {
        console.warn("Could not load glightbox CSS", cssErr);
      }

      const initializeGalleryLightbox = () => {
        try {
          GLightbox({
            selector: ".gallery a.glightbox",
            touchNavigation: true,
            loop: true,
            closeButton: true,
          });
        } catch (err) {
          console.warn("Failed to initialize GLightbox", err);
        }
      };

      if (document.readyState === "loading") {
        document.addEventListener(
          "DOMContentLoaded",
          initializeGalleryLightbox,
          { once: true },
        );
      } else {
        initializeGalleryLightbox();
      }
    } catch (err) {
      console.warn("glightbox not available; gallery lightbox disabled", err);
    }
  }

  init();
})();
