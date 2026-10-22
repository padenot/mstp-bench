## Safari

From WebKit source, 2026-10-23.

| API | Used for | WebKit |
|---|---|---|
| `AudioContext` `sinkId: { type: "none" }` | `audioworklet` and `worker` paths | {{ icon("error-fill") }} Missing. [AudioContextOptions](https://searchfox.org/wubkat/source/Source/WebCore/Modules/webaudio/AudioContextOptions.idl#28) has `latencyHint` and `sampleRate`; [AudioContext](https://searchfox.org/wubkat/source/Source/WebCore/Modules/webaudio/AudioContext.idl#33) has no `sinkId` or `setSinkId()` ([WPT expectations](https://searchfox.org/wubkat/source/LayoutTests/imported/w3c/web-platform-tests/webaudio/idlharness.https.window-expected.txt#61)). |
| `AudioContext` `renderSizeHint` | 512-frame arms | {{ icon("error-fill") }} Missing. [Render quantum fixed at 128 frames](https://searchfox.org/wubkat/source/Source/WebCore/platform/audio/AudioUtilities.h#35). |
| `getOutputTimestamp()` | Playback timing, timestamps | {{ icon("checkmark") }} [Implemented](https://searchfox.org/wubkat/source/Source/WebCore/Modules/webaudio/AudioContext.cpp#220). |
| AudioWorklet, `currentFrame` | All paths | {{ icon("checkmark") }} [Implemented](https://searchfox.org/wubkat/source/Source/WebCore/Modules/webaudio/AudioWorkletGlobalScope.cpp#69). |
| SharedArrayBuffer in worklets and workers | `worker` path, timestamps | {{ icon("checkmark") }} [When cross-origin isolated](https://searchfox.org/wubkat/source/Source/WebCore/bindings/js/SerializedScriptValue.cpp#1141) with COOP/COEP. [Document-Isolation-Policy](https://searchfox.org/wubkat/source/Source/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml#2024) is off by default. |
| MediaRecorder `audio/webm;codecs=opus` | Recording check | {{ icon("checkmark") }} [On by default](https://searchfox.org/wubkat/source/Source/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml#4092) on Apple platforms. |
| Opus, `setCodecPreferences()`, jitter buffer stats | The call | {{ icon("checkmark") }} [Implemented](https://searchfox.org/wubkat/source/Source/WebCore/Modules/mediastream/RTCRtpTransceiver.cpp#108), [including the jitter buffer counters](https://searchfox.org/wubkat/source/Source/WebCore/Modules/mediastream/RTCStatsReport.idl#113). |
| `OffscreenCanvas`, `VideoFrame` in workers | Timestamps | {{ icon("checkmark") }} [Implemented](https://searchfox.org/wubkat/source/Source/WebCore/Modules/webcodecs/WebCodecsVideoFrame.idl#49). |
| Audio MediaStreamTrackProcessor and MediaStreamTrackGenerator | `mstp` path | Chromium only. WebKit’s [MediaStreamTrackProcessor](https://searchfox.org/wubkat/source/Source/WebCore/Modules/mediastream/MediaStreamTrackProcessor.cpp#61) takes video tracks in dedicated workers; its generator is [VideoTrackGenerator](https://searchfox.org/wubkat/source/Source/WebCore/Modules/mediastream/VideoTrackGenerator.idl#31). |
