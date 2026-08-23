# Captor Hub Frontend UI & UX Specification

This document provides the exact margin, padding, size, color, asset-export, and behavioral specifications to replicate the mockups for the **Captor Hub** desktop app. This is optimized for integration with **Google Stitch**.

---

## 1. Grid, Spacing, and Dimensions

The application layout uses a landscape orientation designed for high-resolution displays.

* **App Window Resolution**: `1440px` (width) x `1020px` (height)
* **Window Background**: `#111111`
* **Outer Margins**: `40px` padding on all four edges of the window.

```
 ┌────────────────────────────────────────────────────────┐ ───
 │  1440 x 1020 Window                                    │  ▲
 │                                            [COM] (A) ↻ │  │ 40px
 │  ┌──────────────────────────────────────────────────┐  │  ───
 │  │ TOP CARD (Device & Mode Control)                 │  │  ▲
 │  │                                                  │  │  │ 560px
 │  │                                                  │  │  │
 │  │                                                  │  │  ▼
 │  └──────────────────────────────────────────────────┘  │  ───
 │                                                        │  │ 40px gap
 │  ┌──────────────────────────────────────────────────┐  │  ───
 │  │ BOTTOM CARD (Settings Control Grid & D-pad)       │  │  ▲
 │  │                                                  │  │  │ 280px
 │  │                                                  │  │  ▼
 │  └──────────────────────────────────────────────────┘  │  ───
 └────────────────────────────────────────────────────────┘
    │◄──────────────────── 1360px ────────────────────►│
```

### Top Card (Device & Mode Control Panel)
* **Background**: `#181818`
* **Dimensions**: `1360px` (width) x `560px` (height)
* **Corner Radius (Fillet)**: `24px`
* **Layout**:
  * **Device Status Indicator**: Centered horizontally at the top, `30px` from the card's top edge.
  * **Main Device Mockup**: Centered in the card, taking up the majority of the space.
  * **Mode Selector (CC / GIF / Stats)**: Positioned in the bottom-left corner (`bottom: 30px; left: 30px;`).
  * **Control Pill (Apply & Start/Stop)**: Positioned in the bottom-right corner (`bottom: 30px; right: 30px;`).

### Bottom Card (Settings & Tuning Panel)
* **Background**: `#181818`
* **Dimensions**: `1360px` (width) x `280px` (height)
* **Corner Radius (Fillet)**: `24px`
* **Layout**:
  * **Settings Grid**: Left-aligned, arranged in a structured grid with 2 columns.
    * **Left Margin**: `40px` from the card's left edge.
    * **Vertical Padding**: `30px` from top/bottom.
    * **Row Gap**: `20px` (vertical distance between rows).
    * **Column Gap**: `40px` (horizontal distance between form fields).
  * **Nudge Text D-pad**: Centered vertically in the right-hand section (`right: 60px;`).

---

## 2. Color Palette (Bose Design System)

To maintain absolute visual consistency, use these exact hex codes:

| Color Token | Hex Code | Usage |
| :--- | :--- | :--- |
| **Main Background** | `#111111` | Window background |
| **Card Background** | `#181818` | Primary panel cards (Top & Bottom) |
| **Secondary Background** | `#252525` | Segmented buttons, open dropdowns, closed inputs |
| **Active Highlight Green** | `#11FF00` | Online state LED, ON toggle track, slider active track, hover states |
| **Active Highlight Red** | `#FF0038` | Stop button background, Offline state LED |
| **Active Highlight Orange** | `#FF9100` | Connecting state LED, Staged settings warning indicator |
| **Text Primary (White)** | `#FFFFFF` | Headings, active menu choices |
| **Text Secondary (Muted)** | `#E4E4E4` | Labels, inputs, inactive options |
| **Text Inactive** | `#444444` | Inactive borders, disabled settings |

---

## 3. UI Component Construction & Asset Exports

To build the interface in Google Stitch, divide the visual elements into **custom code components** and **exported graphic assets**:

### A. Export from Affinity Designer (PNG / SVG)
1. **Device Mockup Render (`device_hand.png`)**: A high-resolution, transparency-masked PNG of the Captor X device held in the hand.
2. **D-pad Circular Vector (`dpad_base.svg`)**: The clean, circular D-pad controller body.
3. **D-pad Hover Glows (`glow_up.svg`, `glow_down.svg`, etc.)**: Individual semi-transparent green radial glow overlays matching the curve of the D-pad directions to layer on hover.
4. **Icons (SVG)**:
   * Chevron Down (`v`) and Chevron Up (`^`) for dropdowns.
   * Auto-Connect `(A)` icon badge.
   * Manual Scan icon (rotating circular arrows/reload).
   * Mode Icons: `CC` (Captions), `GIF` (Image), `📈` (Stats chart).

### B. Build from Scratch in Google Stitch (Pure CSS/HTML)
1. **Dropdown Selectors**:
   * Closed: Pill-shaped box, `#252525` background, `#444444` border, height `42px`, width `260px`, `border-radius: 20px`, right-aligned chevron.
   * Open: Options overlay with `#252525` background, rounded corner popups, items highlight on hover with background `#333333`.
2. **Segmented Mode Selector**:
   * Background pill: `#252525` background, `border-radius: 20px`, height `40px`.
   * Internal buttons: Transparent background, white text. The active mode button transitions smoothly to a lighter gray `#383838` background.
3. **Toggle Switches**:
   * Track: Width `56px`, height `26px`, `border-radius: 13px`.
   * Thumb: White circle, diameter `22px`, slides left-to-right (`transition: transform 0.25s ease`).
   * Color transition: Track turns `#11FF00` when ON, and `#252525` (with `#444444` border) when OFF.
4. **Sliders (OLED Brightness & Threshold)**:
   * Track height: `6px`, background `#252525`.
   * Active progress track: Color `#11FF00`.
   * Thumb: White circle, diameter `20px`. Scale up to `24px` on hover with a subtle green outer glow.
5. **Control Pill (Apply / Start-Stop)**:
   * A unified pill (`#252525` container, `border-radius: 27px`, height `54px`, width `140px`).
   * Contains two clickable circular areas:
     1. **Apply Settings**: A circular indicator with a checkmark `(✓)`. Grey `#444444` when saved, warning orange `#FF9100` when dirty, and pulsing green `#11FF00` on successful write.
     2. **Start/Stop**: A circular action button. Idle shows a white play triangle `(▶)`; running turns it into a solid red square `(■)` with background `#FF0038`.

---

## 4. Page Routing & View Management

The frontend operates in two distinct views controlled by user interaction:

### View 1: Devices Page (Initial Load)
* **Purpose**: Allows the user to verify hardware connection before entering configuration.
* **Layout**:
  * The main window is empty except for the top-right COM selection bar.
  * A single, large card is centered in the viewport (`600px` x `560px`).
  * Displays the offline/neutral device mockup and status `● CAPTOR X [ONLINE]`.
  * **Interactivity**: Clicking anywhere on the card initiates a slide-left transition to reveal **View 2**.

### View 2: Main Application Dashboard
* **Purpose**: Configures the active device modes.
* **Transitions**: Triggers when the Devices card is clicked.
* **Dynamic Bottom Panels**: The bottom Settings Card changes layout dynamically based on the active Mode Selector button:
  1. **Caption Mode (`CC`)**: Shows Model, Language, Text Case, Text Alignment, OLED Font, Audio Source, Music Mode, Invert OLED, Display Mode, Welcome Text, and Brightness slider.
  2. **GIF Mode (`GIF`)**: Shows Load GIF (Text entry + File explorer trigger `Browse`), Playback Speed, Dithering selection, Sizing Mode, Invert OLED, and Threshold level slider.
  3. **Stats Mode (`📈`)**: Shows Update Interval dropdown, Dashboard Font selector, and Monitor GPU toggle switch.
  * *Note: The Nudge Text D-pad remains visible on the right across all three modes.*

---

## 5. Micro-Animations and Visual Polish
* **D-pad Hover**: The green glow arches must fade in smoothly (`transition: opacity 0.2s ease`) when the cursor hovers over the corresponding quadrant.
* **Dropdown Transition**: The options list should slide down and fade in (`transform: translateY(-10px) -> translateY(0)`, `opacity: 0 -> 1`) when clicked.
* **State indicator pulse**: The status LED (green/red/orange dot) should have a slow, gentle opacity breathing effect (`animation: pulse 3s infinite ease-in-out`) to feel "alive".
