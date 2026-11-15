# Red Thread

A Video.js 10 skin where the whole player is one piece of string.

- **The timeline is a thread.** Played is red, buffered is white, the rest is faint. Chapters are knots.
- **On pause it draws the play button.** The thread goes slack, rises and folds into a triangle. Click and it snaps tight and rings.
- **You seek by plucking.** Drag the thread and the video follows your hand; let go and it rings like a guitar string. A plain click keeps it tight and the red runs up to the spot. Arrow keys slide the preview along it.
- **The preview hangs from the thread** like a photo on a clothesline, using the media's storyboard track. Move fast and it swings.
- **Captions are two strands** that hang loose when off and pull tight when on. Each caption line is written out with a thread drawn under it.
- **Fullscreen is a thread on four pins.** Click it and four threads reach the corners of the screen, go tight and pull the player open.
- **Volume is a pull cord** in the top corner. Pull down for more, tap to mute.
- **While you watch it almost disappears**: a thin line at the bottom edge that trembles with the sound, and carries a bump along it while the video buffers.

## How it is built

`src/video/skin.html` is a normal Video.js 10 skin: `media-container`, the real `media-play-button`, `media-mute-button`, `media-captions-button`, `media-fullscreen-button`, `media-time-slider`, `media-time`, hotkeys, error dialog and status announcer. Those elements keep the player operable by keyboard and assistive technology.

`src/video/red-thread.ts` defines `<red-thread>`, one canvas over the picture. Every frame it reads the player store (`currentTime`, `duration`, `paused`, `buffered`, `waiting`, `volume`, `muted`, `chaptersCues`, `thumbnailsTrack`, `subtitlesShowing`, `isFullscreen`) and draws the thread; pointer gestures call the store's actions (`play`, `pause`, `seek`, `setVolume`, `setMuted`, `requestFullscreen`). It has no dependencies beyond `@videojs/html`.

`src/video/skin.css` styles the real controls and exposes `--media-accent-color`, `--media-border-radius` and `--media-font-family`.

Reduced motion is respected: no springs, no stretch, no caption wipe.

## Develop

```sh
npm run dev
```

The workbench plays NASA's Cosmic Dawn trailer from Mux, with chapters, captions and a storyboard. Change the media in `apps/preview/src/frame/player`.

```sh
npm run typecheck
npm run build
```

## Deploy

```sh
npm run deploy
```

Made by Valerio Donfrancesco for the Video.js Skins Design Challenge. Started from `videojs skin create` (see `skin.json`).
