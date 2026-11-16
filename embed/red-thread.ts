// The skin as one module for pages without a bundler: the Video.js player, the Mux media element and the skin.
// `npm run build:embed` writes red-thread.js and red-thread.css (plus the language files Video.js loads on
// demand) to dist-embed/; copy that folder to your site and load the two files. The README shows the markup.
import '@videojs/html/video/player';
import '@videojs/html/media/mux-video';
import '../src/video/skin';
