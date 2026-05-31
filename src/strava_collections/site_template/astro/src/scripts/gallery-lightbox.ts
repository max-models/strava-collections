import GLightbox from 'glightbox';
import 'glightbox/dist/css/glightbox.css';

const initializeGalleryLightbox = () => {
  GLightbox({
    selector: '.gallery a.glightbox',
    touchNavigation: true,
    loop: true,
    closeButton: true,
  });
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeGalleryLightbox, { once: true });
} else {
  initializeGalleryLightbox();
}
