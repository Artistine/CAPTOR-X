/**

 * @license

 * SPDX-License-Identifier: Apache-2.0

 */



import React, { useState, useEffect, useRef } from "react";

import mockupImg from "../assets/CAPTOR_X_MOCKUP.png";

import { 

  ChevronDown, 

  RotateCcw, 

  Check, 

  Play, 

  Square,

  RefreshCw,

  FolderOpen

} from "lucide-react";

import { motion, AnimatePresence } from "motion/react";



// Premium custom dropdown block extending the physical gray case downward

interface CustomDropdownProps {

  id?: string;

  value: string;

  options: string[] | { value: string; label: string }[];

  onChange: (value: string) => void;

}



function CustomDropdown({ id, value, options, onChange }: CustomDropdownProps) {

  const [isOpen, setIsOpen] = useState(false);

  const [openUp, setOpenUp] = useState(false);

  const dropdownRef = useRef<HTMLDivElement>(null);



  useEffect(() => {

    const handleClickOutside = (event: MouseEvent) => {

      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {

        setIsOpen(false);

      }

    };

    document.addEventListener("mousedown", handleClickOutside);

    return () => document.removeEventListener("mousedown", handleClickOutside);

  }, []);



  useEffect(() => {

    if (isOpen && dropdownRef.current) {

      const rect = dropdownRef.current.getBoundingClientRect();

      const viewportHeight = window.innerHeight;

      // If the dropdown bottom extends near the lower viewport edge (or has less than 240px space), open UP

      if (rect.bottom + 230 > viewportHeight) {

        setOpenUp(true);

      } else {

        setOpenUp(false);

      }

    }

  }, [isOpen]);



  useEffect(() => {

    // Elevate the z-index of the parent form-group or dropdown-wrapper to prevent stacking order overlap glitches

    if (dropdownRef.current) {

      const container = dropdownRef.current.closest(".form-group") || dropdownRef.current.closest(".dropdown-wrapper");

      if (container) {

        if (isOpen) {

          (container as HTMLElement).style.zIndex = "9999";

        } else {

          (container as HTMLElement).style.zIndex = "";

        }

      }

      // Elevate the parent dashboard card to clear absolute sibling positioning contexts

      const parentCard = dropdownRef.current.closest(".dashboard-bottom-card") || dropdownRef.current.closest(".dashboard-top-card");

      if (parentCard) {

        if (isOpen) {

          (parentCard as HTMLElement).style.zIndex = "9999";

        } else {

          (parentCard as HTMLElement).style.zIndex = "";

        }

      }

    }

  }, [isOpen]);



  const formattedOptions = options.map(opt => 

    typeof opt === "string" ? { value: opt, label: opt } : opt

  );



  const selectedOption = formattedOptions.find(opt => opt.value === value) || formattedOptions[0];



  return (

    <div ref={dropdownRef} className="relative w-full z-[120]">

      <button

        type="button"

        id={id}

        onClick={() => setIsOpen(!isOpen)}

        className={`dropdown text-left flex items-center justify-between px-4 transition-all duration-200 cursor-pointer ${

          isOpen ? "bg-[#333333] border-[#3c3c3c]" : ""

        }`}

        style={{

          borderBottomLeftRadius: isOpen && !openUp ? 0 : undefined,

          borderBottomRightRadius: isOpen && !openUp ? 0 : undefined,

          borderTopLeftRadius: isOpen && openUp ? 0 : undefined,

          borderTopRightRadius: isOpen && openUp ? 0 : undefined,

          borderBottomWidth: isOpen && !openUp ? 0 : undefined,

          borderTopWidth: isOpen && openUp ? 0 : undefined,

          backgroundColor: isOpen ? "var(--bg-control-hover)" : undefined,

          borderColor: isOpen ? "#444444" : undefined

        }}

      >

        <span className="truncate pr-4">{selectedOption ? selectedOption.label : value}</span>

        <ChevronDown 

          className="dropdown-arrow transition-transform duration-250 text-zinc-400" 

          style={{ 

            transform: `translateY(-50%) ${isOpen ? "rotate(180deg)" : "rotate(0deg)"}`,

            color: isOpen ? "var(--color-green)" : undefined

          }}

        />

      </button>



      <AnimatePresence>

        {isOpen && (

          <motion.div

            initial={{ opacity: 0, y: openUp ? 4 : -4, scaleY: 0.92 }}

            animate={{ opacity: 1, y: 0, scaleY: 1 }}

            exit={{ opacity: 0, y: openUp ? 4 : -4, scaleY: 0.92 }}

            transition={{ type: "spring", duration: 0.18, bounce: 0 }}

            style={{ 

              transformOrigin: openUp ? "bottom center" : "top center",

              borderTopWidth: openUp ? undefined : 0,

              borderBottomWidth: openUp ? 0 : undefined,

              backgroundColor: "var(--bg-control-hover)",

              borderColor: "#444444"

            }}

            className={`absolute ${

              openUp ? "bottom-[38px] rounded-t-xl" : "top-[38px] rounded-b-xl"

            } left-0 right-0 border p-1.5 flex flex-col gap-1 z-[999] max-h-[220px] overflow-y-auto no-scrollbar`}

          >

            {formattedOptions.map((opt) => (

              <button

                key={opt.value}

                type="button"

                onClick={() => {

                  onChange(opt.value);

                  setIsOpen(false);

                }}

                className={`w-full text-left px-3 py-2 rounded-lg text-xs font-mono transition-all duration-150 flex items-center justify-between cursor-pointer ${

                  opt.value === value 

                    ? "bg-[#11FF00]/10 text-[#11FF00] font-bold" 

                    : "text-zinc-300 hover:bg-white/5 hover:text-white"

                }`}

              >

                <span className="truncate">{opt.label}</span>

                {opt.value === value && <Check className="w-3.5 h-3.5 text-[#11FF00]" />}

              </button>

            ))}

          </motion.div>

        )}

      </AnimatePresence>

    </div>

  );

}



// Declared Types for Form Settings

interface CCSettings {

  model: string;

  textCase: string;

  oledFont: string;

  audioSource: string;

  language: string;

  alignment: string;

  brightness: number;

  musicMode: boolean;
  visualizer: string;

  invertOled: boolean;

  displayMode: string;

  welcomeText: string;
  autoStart: boolean;
}



interface GifSettings {

  gifPath: string;

  threshold: number;

  speed: string;

  dithering: string;

  invertGif: boolean;

  sizingMode: string;

}



interface StatsSettings {

  interval: string;

  statsFont: string;

  monitorGpu: boolean;

  layout: string;

  cpuMinMhz: number;

  cpuMaxMhz: number;

  gpuMinWatt: number;

  gpuMaxWatt: number;

}

interface ClockSettings {
  clockFormat: string;
  clockAnimation: string;
  clockTheme: string;
}

const checkIsNative = (): boolean => {
  return typeof (window as any).pywebview !== "undefined" && 
         typeof (window as any).pywebview.api !== "undefined" && 
         typeof (window as any).pywebview.api.get_settings !== "undefined" && 
         !(window as any).pywebview.api.isMock;
};
(window as any).checkIsNative = checkIsNative;

export default function App() {

  const [comPort, setComPort] = useState<string>("COM 1");

  const [comPorts, setComPorts] = useState<string[]>(["COM 1", "COM 2", "COM 3"]);

  const [audioSources, setAudioSources] = useState<string[]>(["Speakers [8-AI-04]", "Microphone [Realtek]", "Virtual Audio Cable"]);

  const [isAutoConnect, setIsAutoConnect] = useState<boolean>(false);

  const [connectionStatus, setConnectionStatus] = useState<"connected" | "disconnected" | "connecting">("disconnected");



  const fontsList = [

    "Vin Mono Pro (Thin)",

    "Pixellari",

    "VCR OSD",

    "blipfest 07",

    "bipixel double",

    "bpixel",

    "bytesize",

    "cubemel",

    "doomalpha04",

    "freedoomr10"

  ];

  const [isScanning, setIsScanning] = useState<boolean>(false);



  // CC Mode Settings State

  const [ccSettings, setCcSettings] = useState<CCSettings>({

    model: "tiny.en",

    textCase: "UPPERCASE",

    oledFont: "Vin Mono Pro (Thin)",

    audioSource: "Speakers [8-AI-04]",

    language: "English",

    alignment: "Center",

    brightness: 200,

    musicMode: false,
    visualizer: "Tape Graphics",

    invertOled: true,

    displayMode: "Word by Word",

    welcomeText: "ACTIVE",
    autoStart: false
  });



  // GIF Mode Settings State

  const [gifSettings, setGifSettings] = useState<GifSettings>({

    gifPath: "D:\\downloads\\captioncast\\captioncast\\refs\\Flat.gif",

    threshold: 128,

    speed: "1.5 x",

    dithering: "Threshold",

    invertGif: true,

    sizingMode: "Stretch"

  });



  // Stats Mode Settings State

  const [statsSettings, setStatsSettings] = useState<StatsSettings>({

    interval: "0.5s",

    statsFont: "U8g2 Pixellari",

    monitorGpu: true,

    layout: "CPU",

    cpuMinMhz: 3600,

    cpuMaxMhz: 4200,

    gpuMinWatt: 30,

    gpuMaxWatt: 180

  });



  // Clock Mode Settings State

  const [clockSettings, setClockSettings] = useState<ClockSettings>({
    clockFormat: "12-Hour",
    clockAnimation: "Snappy Easing",
    clockTheme: "OBSEDIAN"
  });




  // Active Dashboard Panel (CC, GIF, Stats)

  const [activeMode, setActiveMode] = useState<"cc" | "gif" | "stats" | "clk">("cc");



  // Dirty state tracker for Applied changes

  const [isDirty, setIsDirty] = useState<boolean>(false);

  const [applyState, setApplyState] = useState<"idle" | "success">("idle");

  const [isRunning, setIsRunning] = useState<boolean>(false);

  const [runningMode, setRunningMode] = useState<"cc" | "gif" | "stats" | "clk" | null>(null);



  // Precise offset of OLED screen text nudge state (controlled by D-Pad)

  const [nudgeOffset, setNudgeOffset] = useState({ x: 0, y: 0 });



  // Browser scaling dimensions calculation

  const [dimensions, setDimensions] = useState({ w: window.innerWidth, h: window.innerHeight });



  // Custom simulation modals

  const [showFileModal, setShowFileModal] = useState<boolean>(false);



  // References

  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const animationRef = useRef<number | null>(null);

  const textUpdateTimerRef = useRef<NodeJS.Timeout | null>(null);



  // Dynamic OLED Live display state

  const [oledText, setOledText] = useState<string>("WELCOME [ACTIVE]");



  // Pre-load mock audio speech phrases for live transcriptions

  const speechPhrases = [

    "STITCH ENGINE ENGAGED",

    "CAPTION DECODER RUNNING",

    "DEEP VOICE STREAM DETECTED",

    "WHISPER MODEL INGESTING AUDIO",

    "STYLING OLED CHARS LIVE",

    "ACTIVE CAPTOR X STATUS GREEN",

    "SYNCHRONIZING TRANSLATION",

    "BOSE RETRO HARDWARE ACTIVE",

    "PROCESSING AUDIO CHANNELS"

  ];

  const phraseIndexRef = useRef<number>(0);



  // Dynamic window resizing scale calculation (Maintains exact 1440x1020 perspective inside standard viewport)

  useEffect(() => {

    const handleResize = () => {

      setDimensions({ w: window.innerWidth, h: window.innerHeight });

    };

    window.addEventListener("resize", handleResize);

    return () => window.removeEventListener("resize", handleResize);

  }, []);



  const scale = Math.min(dimensions.w / 1440, dimensions.h / 1020);



  // Expose pywebview API bridge object directly for native execution boundary compatibility

  useEffect(() => {

    // Bind frame updates

    (window as any).drawScreenFrame = (base64Img: string) => {

      const canvas = canvasRef.current;

      if (!canvas) return;

      const ctx = canvas.getContext("2d");

      if (!ctx) return;

      

      const img = new Image();

      img.onload = () => {

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      };

      img.src = "data:image/png;base64," + base64Img;

    };

    (window as any).updateConnectionStatus = (status: "connected" | "disconnected" | "connecting") => {
      setConnectionStatus(status);
    };

    (window as any).cycleModeTo = (mode: string) => {
      let tab: "cc" | "gif" | "stats" | "clk" = 'cc';
      if (mode === 'GIF PLAYER') tab = 'gif';
      else if (mode === 'PC STATS') tab = 'stats';
      else if (mode === 'CLK') tab = 'clk';
      setActiveMode(tab);
      setCcSettings(prev => ({ ...prev, mode: mode }));
      setRunningMode(tab);
      setIsDirty(false);
    };

    (window as any).toggleMusicModeAndCC = (enabled: boolean) => {
      setActiveMode('cc');
      setCcSettings(prev => ({ ...prev, mode: 'CAPTIONS', musicMode: enabled }));
      setRunningMode('cc');
      setIsDirty(false);
    };

    (window as any).updateStatsLayout = (layout: string) => {
      setStatsSettings(prev => ({ ...prev, layout }));
      setIsDirty(false);
    };

    (window as any).updateGifPath = (path: string) => {
      setGifSettings(prev => ({ ...prev, gifPath: path }));
      setIsDirty(false);
    };



    let intervalId: any = null;

    let nativeListener: any = null;



    const initApp = async () => {
      const api = (window as any).pywebview.api;

      try {
        // 1. Get Serial Ports
        if (api.get_serial_ports) {
          const ports = await api.get_serial_ports();
          setComPorts(ports);
        }

        // Query initial connection status
        if (api.get_connection_status) {
          const initialStatus = await api.get_connection_status();
          setConnectionStatus(initialStatus);
        } else {
          // Fallback guess based on active com port setting
          if (api.get_settings) {
            const settings = await api.get_settings();
            if (settings.com_port && settings.com_port !== "None") {
              setConnectionStatus("connected");
            } else {
              setConnectionStatus("disconnected");
            }
          }
        }

        // 2. Get Audio Sources
        if (api.get_audio_sources) {
          const sources = await api.get_audio_sources();
          setAudioSources(sources);
        }

        // 3. Get Settings
        if (api.get_settings) {
          const s = await api.get_settings();

          if (s.com_port) setComPort(s.com_port);

          if (s.current_mode) {
            const m = s.current_mode.toLowerCase();
            if (m === "captions" || m === "cc") setActiveMode("cc");
            else if (m === "gif player" || m === "gif") setActiveMode("gif");
            else if (m === "pc stats" || m === "stats") setActiveMode("stats");
            else if (m === "clk" || m === "clock") setActiveMode("clk");
          }

          setCcSettings({
            model: s.model || "tiny.en",
            textCase: s.text_case || "UPPERCASE",
            oledFont: s.oled_font || "Vin Mono Pro (Thin)",
            audioSource: s.audio_source || "",
            language: s.language || "English",
            alignment: s.alignment ? (s.alignment.charAt(0).toUpperCase() + s.alignment.slice(1)) : "Center",
            brightness: s.brightness !== undefined ? s.brightness : 200,
            musicMode: s.music_mode || false,
            visualizer: s.visualizer || "Tape Graphics",
            invertOled: s.invert_oled || false,
            displayMode: s.display_mode || "Word by Word",
            welcomeText: s.welcome_text || "ACTIVE",
            autoStart: s.auto_start || false
          });

          setGifSettings({
            gifPath: s.gif_path || "",
            threshold: s.gif_threshold !== undefined ? s.gif_threshold : 128,
            speed: s.gif_speed || "1.0x (Normal)",
            dithering: s.gif_dithering || "Threshold",
            invertGif: s.invert_gif || false,
            sizingMode: s.gif_sizing || "Aspect Ratio"
          });

          setStatsSettings({
            interval: s.stats_interval || "1.0s (Normal)",
            statsFont: s.stats_font || "Proggy Tiny",
            monitorGpu: s.monitor_gpu !== undefined ? s.monitor_gpu : true,
            layout: s.stats_layout || "CPU",
            cpuMinMhz: s.cpu_min_mhz !== undefined ? s.cpu_min_mhz : 3600,
            cpuMaxMhz: s.cpu_max_mhz !== undefined ? s.cpu_max_mhz : 4200,
            gpuMinWatt: s.gpu_min_watt !== undefined ? s.gpu_min_watt : 30,
            gpuMaxWatt: s.gpu_max_watt !== undefined ? s.gpu_max_watt : 180
          });

          setClockSettings({
            clockFormat: s.clock_format || "12-Hour",
            clockAnimation: s.clock_animation || "Snappy Easing",
            clockTheme: s.clock_theme || "OBSEDIAN"
          });
        }
      } catch (err) {
        console.error("Error loading initial pywebview settings:", err);
      }
    };



    const isViteDev = window.location.port === "5173" || window.location.port === "5174";



    if (isViteDev) {

      console.log("Vite development server detected. Initializing mock API.");

      (window as any).pywebview = {

        api: {

          isMock: true,

          get_serial_ports: async () => ["None", "COM 1", "COM 2", "COM 3"],

          get_audio_sources: async () => ["Speakers [8-AI-04]", "Microphone [Realtek]", "Virtual Audio Cable"],

          get_connection_status: async () => "disconnected",

          get_settings: async () => ({}),

          start_captioning: async () => {

            setIsRunning(true);

            setRunningMode(activeMode);

            return true;

          },

          stop_captioning: async () => {

            setIsRunning(false);

            setRunningMode(null);

            return true;

          },

          apply_settings: async (settings: any) => {

            console.log("Settings applied asynchronously to PyWebView (Mock):", settings);

            return { status: "success", settings };

          },

          browse_gif: async () => "",

          nudge_text: async (dir: string) => ({ x: 0, y: 0 }),

          change_mode: async (modeName: string) => {

            console.log("Mode changed (Mock):", modeName);

          }

        }

      };

      initApp();

    } else {
      const tryNativeInit = () => {
        if (
          typeof (window as any).pywebview !== "undefined" &&
          typeof (window as any).pywebview.api !== "undefined" &&
          typeof (window as any).pywebview.api.get_settings !== "undefined" &&
          !(window as any).pywebview.api.isMock
        ) {
          initApp();

          if (intervalId) {
            clearInterval(intervalId);
          }

          window.removeEventListener("pywebviewready", tryNativeInit);
          return true;
        }
        return false;
      };

      if (!tryNativeInit()) {
        nativeListener = tryNativeInit;
        window.addEventListener("pywebviewready", tryNativeInit);
        intervalId = setInterval(tryNativeInit, 20);
      }
    }



    return () => {

      if (intervalId) clearInterval(intervalId);

      if (nativeListener) window.removeEventListener("pywebviewready", nativeListener);

      delete (window as any).drawScreenFrame;

      delete (window as any).updateConnectionStatus;

      delete (window as any).cycleModeTo;
      delete (window as any).toggleMusicModeAndCC;
      delete (window as any).updateStatsLayout;
      delete (window as any).updateGifPath;

    };

  }, []);



  // Sync settings modifications to trigger Apply dirty warning state

  const flagSettingsDirty = () => {

    setIsDirty(true);

  };



  // Trigger brief success animation on apply settings button

  const handleApplyClick = () => {

    setApplyState("success");

    setIsDirty(false);

    

    // Call pywebview interface

    if ((window as any).pywebview?.api?.apply_settings) {

      const payload = {

        com_port: comPort,

        model: ccSettings.model,

        text_case: ccSettings.textCase,

        oled_font: ccSettings.oledFont,

        audio_source: ccSettings.audioSource,

        language: ccSettings.language,

        alignment: ccSettings.alignment.toLowerCase(),

        brightness: ccSettings.brightness,

        music_mode: ccSettings.musicMode,
        visualizer: ccSettings.visualizer,

        invert_oled: ccSettings.invertOled,

        display_mode: ccSettings.displayMode,

        welcome_text: ccSettings.welcomeText,
        auto_start: ccSettings.autoStart,

        

        gif_path: gifSettings.gifPath,

        gif_threshold: gifSettings.threshold,

        gif_speed: gifSettings.speed,

        gif_dithering: gifSettings.dithering,

        invert_gif: gifSettings.invertGif,

        gif_sizing: gifSettings.sizingMode,

        

        stats_interval: statsSettings.interval,

        stats_font: statsSettings.statsFont,

        monitor_gpu: statsSettings.monitorGpu,

        stats_layout: statsSettings.layout,

        cpu_min_mhz: statsSettings.cpuMinMhz,

        cpu_max_mhz: statsSettings.cpuMaxMhz,

        gpu_min_watt: statsSettings.gpuMinWatt,

        gpu_max_watt: statsSettings.gpuMaxWatt,

        clock_format: clockSettings.clockFormat,
        clock_animation: clockSettings.clockAnimation,
        clock_theme: clockSettings.clockTheme,

        current_mode: activeMode === "cc" ? "CAPTIONS" : activeMode === "gif" ? "GIF PLAYER" : activeMode === "stats" ? "PC STATS" : "CLK"

      };

      (window as any).pywebview.api.apply_settings(payload);

    }



    setTimeout(() => {

      setApplyState("idle");

    }, 1000);

  };



  // Start / Stop Caption decoders

  const handleStartStopClick = async () => {

    const isCurrentModeRunning = runningMode === activeMode;

    const api = (window as any).pywebview?.api;

    

    if (isCurrentModeRunning) {

      setRunningMode(null);

      setIsRunning(false);

      if (api?.stop_captioning) {

        await api.stop_captioning();

      }

    } else {

      if (runningMode !== null && api?.stop_captioning) {

        await api.stop_captioning();

      }

      if (api?.change_mode) {

        const modeMap = {
          cc: "CAPTIONS",
          gif: "GIF PLAYER",
          stats: "PC STATS",
          clk: "CLK"
        };

        await api.change_mode(modeMap[activeMode]);

      }

      setRunningMode(activeMode);

      setIsRunning(true);

      if (api?.start_captioning) {

        await api.start_captioning();

      }

    }

  };



  // Trigger COM rescan query

  const handleRescanClick = async () => {

    setIsScanning(true);

    const isNative = checkIsNative();

    if (isNative && (window as any).pywebview.api.get_serial_ports) {

      try {

        const ports = await (window as any).pywebview.api.get_serial_ports();

        setComPorts(ports);

      } catch (err) {

        console.error("Error scanning serial ports:", err);

      }

    } else {

      // Fallback/Mock

      await new Promise(resolve => setTimeout(resolve, 700));

      setComPorts(["COM 1", "COM 2", "COM 3", "COM 4", "COM 5"]);

    }

    setIsScanning(false);

  };



  // Update real-time text scroll based on active states

  useEffect(() => {

    // Disable mock text changes in pywebview

    const isNative = checkIsNative();

    if (isNative) {

      setOledText("");

      return;

    }



    if (!isRunning) {

      if (activeMode === "cc") {

        setOledText(ccSettings.welcomeText ? `WELCOME [${ccSettings.welcomeText}]` : "READY");

      } else if (activeMode === "gif") {

        setOledText("GIF PLAYER READY");

      } else {

        setOledText("METRICS DISPLAY RUNNING");

      }

      if (textUpdateTimerRef.current) clearInterval(textUpdateTimerRef.current);

      return;

    }



    // Set active ticker running

    if (activeMode === "cc") {

      setOledText(speechPhrases[0]);

      textUpdateTimerRef.current = setInterval(() => {

        phraseIndexRef.current = (phraseIndexRef.current + 1) % speechPhrases.length;

        setOledText(speechPhrases[phraseIndexRef.current]);

      }, 2500);

    } else if (activeMode === "gif") {

      setOledText(`PLAYING: ${gifSettings.gifPath.split("\\").pop()}`);

    } else {

      setOledText("GPU: 52°C | CPU: 47°C");

      textUpdateTimerRef.current = setInterval(() => {

        const randGpu = Math.floor(48 + Math.random() * 8);

        const randCpu = Math.floor(42 + Math.random() * 10);

        const load = Math.floor(10 + Math.random() * 15);

        setOledText(`GPU: ${randGpu}°C | CPU: ${randCpu}°C | LD: ${load}%`);

      }, 1500);

    }



    return () => {

      if (textUpdateTimerRef.current) clearInterval(textUpdateTimerRef.current);

    };

  }, [isRunning, activeMode, ccSettings.welcomeText, gifSettings.gifPath]);



  // Gorgeous 30fps HTML5 Canvas waveform oscilloscope / visualizer render looping

  useEffect(() => {

    // Disable mock render oscilloscope loop in pywebview

    const isNative = checkIsNative();

    if (isNative) return;



    const canvas = canvasRef.current;

    if (!canvas) return;

    const ctx = canvas.getContext("2d");

    if (!ctx) return;



    let localPhase = 0;



    const renderWave = () => {

      const w = canvas.width; // 128

      const h = canvas.height; // 64

      ctx.clearRect(0, 0, w, h);

      

      const isInverted = (activeMode === "cc" && ccSettings.invertOled) || (activeMode === "gif" && gifSettings.invertGif);

      const bgColor = isInverted ? "#11FF00" : "#0c0c0c";

      const fgColor = isInverted ? "#0c0c0c" : "#11FF00";

      

      // Screen background

      ctx.fillStyle = bgColor;

      ctx.fillRect(0, 0, w, h);



      if (isRunning) {

        if (activeMode === "cc") {

          ctx.strokeStyle = fgColor;

          ctx.lineWidth = 1;

          ctx.beginPath();

          localPhase += 0.15;

          for (let x = 0; x < w; x++) {

            const normX = x / w;

            const amp = Math.sin(normX * Math.PI) * 12;

            const y = 32 + Math.sin(normX * 8 + localPhase) * amp;

            if (x === 0) ctx.moveTo(x, y);

            else ctx.lineTo(x, y);

          }

          ctx.stroke();

        } else if (activeMode === "gif") {

          // Blocky digital grid

          ctx.fillStyle = fgColor;

          localPhase += 0.15;

          const cols = 16;

          const rows = 8;

          const cellW = w / cols;

          const cellH = h / rows;

          for (let r = 0; r < rows; r++) {

            for (let c = 0; c < cols; c++) {

              if (Math.sin(c * 0.6 + r * 0.4 + localPhase) > 0.2) {

                ctx.fillRect(c * cellW + 1, r * cellH + 1, cellW - 2, cellH - 2);

              }

            }

          }

        } else if (activeMode === "stats") {

          // stats view standby wave

          ctx.strokeStyle = fgColor;

          ctx.lineWidth = 1;

          ctx.beginPath();

          localPhase += 0.1;

          for (let x = 0; x < w; x++) {

            const normX = x / w;

            const amp = Math.sin(normX * Math.PI) * 8;

            const y = 32 + Math.sin(normX * 5 + localPhase) * amp;

            if (x === 0) ctx.moveTo(x, y);

            else ctx.lineTo(x, y);

          }

          ctx.stroke();

        }

      } else {

        // standby horizontal line

        ctx.strokeStyle = fgColor;

        ctx.lineWidth = 1;

        ctx.beginPath();

        ctx.moveTo(0, 32);

        ctx.lineTo(w, 32);

        ctx.stroke();

      }



      // Draw mock text on the 128x64 canvas

      if (oledText) {

        ctx.fillStyle = fgColor;

        ctx.font = '9px "Courier New", Courier, monospace';

        ctx.textAlign = "center";

        ctx.textBaseline = "middle";

        ctx.fillText(oledText, w / 2 + nudgeOffset.x, h / 2 + nudgeOffset.y);

      }



      animationRef.current = requestAnimationFrame(renderWave);

    };



    renderWave();



    return () => {

      if (animationRef.current) cancelAnimationFrame(animationRef.current);

    };

  }, [isRunning, activeMode, ccSettings.invertOled, gifSettings.invertGif, oledText, nudgeOffset]);



  // Simulated browser GIF file browse options

  const localGifsAvailable = [

    "D:\\downloads\\captioncast\\refs\\Flat.gif",

    "C:\\Users\\User\\Pictures\\PixelMatrices\\8bit_matrix.gif",

    "C:\\Users\\User\\Pictures\\RetroTech\\bouncing_ball.gif",

    "D:\\StitchProProjects\\CaptorX\\glowing_runner.gif"

  ];



  const handleSelectLocalGif = (path: string) => {

    setGifSettings(prev => ({ ...prev, gifPath: path }));

    flagSettingsDirty();

    setShowFileModal(false);

  };



  // Individual D-pad directional nudge controllers

  const handleNudge = (direction: "up" | "left" | "right" | "down" | "reset") => {

    if ((window as any).pywebview?.api?.nudge_text) {

      (window as any).pywebview.api.nudge_text(direction);

    }



    if (direction === "reset") {

      setNudgeOffset({ x: 0, y: 0 });

    } else {

      setNudgeOffset(prev => {

        let { x, y } = prev;

        const step = 4;

        if (direction === "up") y = Math.max(-25, y - step);

        if (direction === "down") y = Math.min(15, y + step);

        if (direction === "left") x = Math.max(-50, x - step);

        if (direction === "right") x = Math.min(50, x + step);

        return { x, y };

      });

    }

  };



  // Hover states tracking for D-pad green quadrant glows

  const [dpadHovered, setDpadHovered] = useState<"up" | "left" | "right" | "down" | null>(null);



  return (

    <div className="viewport-shell">

      {/* Decorative Blueprint Micro Grid Backdrop */}

      <div className="shell-grid-decor"></div>



      {/* Main 1440x1020 Canvas Frame Container */}

      <div 

        className="app-container"

        style={{ transform: `scale(${scale})` }}

      >

        <AnimatePresence mode="wait">

          {/* VIEW 2: Core Dashboard controller console */}

          <motion.main 

            key="dashboard"

            initial={{ opacity: 0, scale: 1.04, filter: "blur(6px)" }}

            animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}

            exit={{ opacity: 0, scale: 1.04, filter: "blur(6px)" }}

            transition={{ type: "spring", duration: 0.55, bounce: 0.08 }}

            id="view-dashboard" 

            className="view active"

          >

            {/* Top Card: Live mechanical Device display viewport & Mode controls */}

            <div className="dashboard-top-card relative">

              <div className="status-indicator-dashboard">

                  <span className={`status-dot ${
                    connectionStatus === "connected" ? "green" :
                    connectionStatus === "connecting" ? "yellow" : "red"
                  }`}></span>

                  <span className="status-text text-white">
                    CAPTOR X{" "}
                    <span className={
                      connectionStatus === "connected" ? "status-connected" :
                      connectionStatus === "connecting" ? "status-connecting" :
                      "status-disconnected"
                    }>
                      {connectionStatus === "connected" && "[CONNECTED]"}
                      {connectionStatus === "connecting" && "[CONNECTING]"}
                      {connectionStatus === "disconnected" && "[DISCONNECTED]"}
                    </span>
                  </span>

                </div>



                {/* COM Connection Section integrated beautifully at top right of the device division */}

                <div className="absolute top-[30px] right-[45px] flex items-center gap-3 z-50">

                  <div className="dropdown-wrapper">

                    <CustomDropdown 

                      id="com-port-selector" 

                      value={comPort}

                      options={comPorts}

                      onChange={(val) => {

                        setComPort(val);

                        flagSettingsDirty();

                      }}

                    />

                  </div>



                  <button 

                    id="auto-connect-btn" 

                    className={`icon-btn ${isAutoConnect ? "active" : ""}`}

                    style={{ height: "38px", width: "38px" }}

                    title="Toggle Auto Connect"

                    onClick={() => setIsAutoConnect(!isAutoConnect)}

                  >

                    <span className="font-mono text-[14px] font-bold leading-none select-none">A</span>

                  </button>



                  <button 

                    id="rescan-btn" 

                    className={`icon-btn ${isScanning ? "animate-spin text-green-400" : ""}`}

                    style={{ height: "38px", width: "38px" }}

                    title="Rescan Ports"

                    onClick={handleRescanClick}

                  >

                    <RefreshCw className="w-4.5 h-4.5" />

                  </button>

                </div>



                <div className="device-preview-wrapper flex justify-center items-center py-6">
                  <div className="relative flex justify-center items-center" style={{ width: "790px", height: "442px" }}>
                      <canvas 
                        ref={canvasRef} 
                        id="live-visualizer-canvas" 
                        width="128" 
                        height="64"
                        className="absolute block bg-black"
                        style={{ 
                          left: "228px", 
                          top: "135px", 
                          width: "334px", 
                          height: "165px", 
                          imageRendering: "pixelated",
                          zIndex: 0
                        }}
                      />
                      <img 
                        src={mockupImg} 
                        alt="Captor X Mockup" 
                        className="absolute inset-0 w-full h-full object-cover pointer-events-none"
                        style={{ zIndex: 10 }}
                      />
                  </div>
                </div>



                {/* Mode Switch Pills */}

                <div className="mode-selector-pill">

                  <button 

                    id="mode-cc" 

                    className={`mode-btn ${activeMode === "cc" ? "active" : ""}`}

                    onClick={() => { 

                      setActiveMode("cc"); 

                      setIsDirty(false); 

                      if (!runningMode && (window as any).pywebview?.api?.change_mode) {

                        (window as any).pywebview.api.change_mode("CAPTIONS");

                      }

                    }}

                  >

                    {activeMode === "cc" && (

                      <motion.div 

                        layoutId="active-mode-indicator" 

                        className="absolute inset-0 bg-[#242524] rounded-[16px] pointer-events-none"

                        transition={{ type: "spring", stiffness: 380, damping: 30 }}

                      />

                    )}

                    <span className="relative z-10">CC</span>

                  </button>

                  <button 

                    id="mode-gif" 

                    className={`mode-btn ${activeMode === "gif" ? "active" : ""}`}

                    onClick={() => { 

                      setActiveMode("gif"); 

                      setIsDirty(false); 

                      if (!runningMode && (window as any).pywebview?.api?.change_mode) {

                        (window as any).pywebview.api.change_mode("GIF PLAYER");

                      }

                    }}

                  >

                    {activeMode === "gif" && (

                      <motion.div 

                        layoutId="active-mode-indicator" 

                        className="absolute inset-0 bg-[#242524] rounded-[16px] pointer-events-none"

                        transition={{ type: "spring", stiffness: 380, damping: 30 }}

                      />

                    )}

                    <span className="relative z-10">GIF</span>

                  </button>

                  <button 

                    id="mode-stats" 

                    className={`mode-btn ${activeMode === "stats" ? "active" : ""}`}

                    onClick={() => { 

                      setActiveMode("stats"); 

                      setIsDirty(false); 

                      if (!runningMode && (window as any).pywebview?.api?.change_mode) {

                        (window as any).pywebview.api.change_mode("PC STATS");

                      }

                    }}

                  >

                    {activeMode === "stats" && (

                      <motion.div 

                        layoutId="active-mode-indicator" 

                        className="absolute inset-0 bg-[#242524] rounded-[16px] pointer-events-none"

                        transition={{ type: "spring", stiffness: 380, damping: 30 }}

                      />

                    )}

                    <span className="relative z-10">STATS</span>

                  </button>

                  <button 

                    id="mode-clk" 

                    className={`mode-btn ${activeMode === "clk" ? "active" : ""}`}

                    onClick={() => { 

                      setActiveMode("clk"); 

                      setIsDirty(false); 

                      if (!runningMode && (window as any).pywebview?.api?.change_mode) {

                        (window as any).pywebview.api.change_mode("CLK");

                      }

                    }}

                  >

                    {activeMode === "clk" && (

                      <motion.div 

                        layoutId="active-mode-indicator" 

                        className="absolute inset-0 bg-[#242524] rounded-[16px] pointer-events-none"

                        transition={{ type: "spring", stiffness: 380, damping: 30 }}

                      />

                    )}

                    <span className="relative z-10">CLK</span>

                  </button>

                </div>



                {/* Action Pill Controller (Apply changes & Run stream) */}

                <div className="action-control-pill">

                  <button 

                    id="action-apply" 

                    className={`apply-btn ${isDirty ? "dirty" : ""} ${applyState === "success" ? "success text-zinc-950" : ""}`}

                    title="Apply Settings"

                    onClick={handleApplyClick}

                  >

                    {applyState === "success" ? <Check className="w-5 h-5 pointer-events-none" /> : "✓"}

                  </button>

                  <button 

                    id="action-start-stop" 

                    className={`start-btn ${runningMode === activeMode ? "running" : "stopped"}`}

                    title={runningMode === activeMode ? "Stop Stream" : "Start Stream"}

                    onClick={handleStartStopClick}

                  >

                    {runningMode === activeMode ? <Square className="w-5 h-5 fill-white pointer-events-none" /> : <Play className="w-5 h-5 fill-white ml-0.5 pointer-events-none" />}

                  </button>

                </div>

              </div>



              {/* Bottom Card: Dynamic Settings Grid form layouts and D-pad joystick */}

              <div className="dashboard-bottom-card">

                

                {/* Left Box: Active mode layouts */}

                <div className="settings-form-container overflow-visible">

                  <AnimatePresence mode="wait">

                    {activeMode === "cc" && (

                      /* SUBPANEL 1: Realtime AI Captions (CC) */

                      <motion.div 

                        key="panel-cc"

                        initial={{ opacity: 0, y: 12, filter: "blur(2px)" }}

                        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}

                        exit={{ opacity: 0, y: -12, filter: "blur(2px)" }}

                        transition={{ type: "spring", duration: 0.35, bounce: 0 }}

                        id="panel-cc" 

                        className="settings-panel active"

                      >

                        <div className="form-row">

                          <div className="form-group">

                            <label>Model</label>

                            <CustomDropdown 

                              id="dropdown-model"

                              value={ccSettings.model}

                              options={["tiny.en", "tiny", "base.en", "base", "small.en", "small"]}

                              onChange={(val) => {

                                setCcSettings(prev => ({ ...prev, model: val }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>



                          <div className="form-group">

                            <label>Text Case</label>

                            <CustomDropdown 

                              id="dropdown-case"

                              value={ccSettings.textCase}

                              options={["UPPERCASE", "lowercase", "Sentence case", "Title Case"]}

                              onChange={(val) => {

                                setCcSettings(prev => ({ ...prev, textCase: val }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>



                          <div className="form-group">

                            <label>OLED Font</label>

                            <CustomDropdown 

                              id="dropdown-font"

                              value={ccSettings.oledFont}

                              options={fontsList}

                              onChange={(val) => {

                                setCcSettings(prev => ({ ...prev, oledFont: val }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>



                          <div className="form-group">

                            <label>Audio Source</label>

                            <CustomDropdown 

                              id="dropdown-source"

                              value={ccSettings.audioSource}

                              options={audioSources}

                              onChange={(val) => {

                                setCcSettings(prev => ({ ...prev, audioSource: val }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>

                        </div>



                        <div className="form-row">

                          <div className="form-group">

                            <label>Language</label>

                            <CustomDropdown 

                              id="dropdown-language"

                              value={ccSettings.language}

                              options={["English", "Spanish", "French", "Japanese", "German"]}

                              onChange={(val) => {

                                setCcSettings(prev => ({ ...prev, language: val }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>



                          <div className="form-group">

                            <label>Text Alignment</label>

                            <CustomDropdown 

                              id="dropdown-alignment"

                              value={ccSettings.alignment}

                              options={["Center", "Left", "Right"]}

                              onChange={(val) => {

                                setCcSettings(prev => ({ ...prev, alignment: val }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>



                          <div className="form-group slider-group">

                            <label>OLED Brightness</label>

                            <div className="slider-fill-wrapper">

                              <div className="relative w-full flex items-center h-8">

                                <div className="slider-track-background" />

                                <div 

                                  className="slider-track-glow"

                                  style={{ width: `${(ccSettings.brightness / 255) * 100}%` }}

                                />

                                <input 

                                  type="range" 

                                  id="slider-brightness" 

                                  className="slider"

                                  min="0" 

                                  max="255" 

                                  value={ccSettings.brightness}

                                  onChange={(e) => {
                                    const val = parseInt(e.target.value);
                                    setCcSettings(prev => ({ ...prev, brightness: val }));
                                    flagSettingsDirty();
                                    if ((window as any).pywebview?.api?.update_brightness) {
                                      (window as any).pywebview.api.update_brightness(val);
                                    }
                                  }}

                                />

                              </div>

                            </div>

                          </div>



                          <div className="form-group input-group">

                            <label>Welcome Text</label>

                            <input 

                              type="text" 

                              id="input-welcome-text" 

                              className="text-input" 

                              value={ccSettings.welcomeText}

                              onChange={(e) => {

                                setCcSettings(prev => ({ ...prev, welcomeText: e.target.value }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>


                        </div>



                        <div className="form-row">

                          <div className="form-group toggle-group">

                            <label>Music Mode</label>

                            <div className="toggle-container">

                              <div 

                                id="toggle-music-mode" 

                                className={`toggle-switch ${ccSettings.musicMode ? "on" : ""}`}

                                onClick={() => {

                                  setCcSettings(prev => ({ ...prev, musicMode: !prev.musicMode }));

                                  flagSettingsDirty();

                                }}

                              >

                                <div className="toggle-handle" />

                              </div>

                            </div>

                          </div>



                          <div className="form-group toggle-group text-nowrap">

                            <label>Invert OLED</label>

                            <div className="toggle-container">

                              <div 

                                id="toggle-invert-oled" 

                                className={`toggle-switch ${ccSettings.invertOled ? "on" : ""}`}

                                onClick={() => {

                                  setCcSettings(prev => ({ ...prev, invertOled: !prev.invertOled }));

                                  flagSettingsDirty();

                                }}

                              >

                                <div className="toggle-handle" />

                              </div>

                            </div>

                          </div>



                          <div className="form-group toggle-group text-nowrap">

                            <label>Auto Start</label>

                            <div className="toggle-container">

                              <div 

                                id="toggle-auto-start" 

                                className={`toggle-switch ${ccSettings.autoStart ? "on" : ""}`}

                                onClick={() => {

                                  setCcSettings(prev => ({ ...prev, autoStart: !prev.autoStart }));

                                  flagSettingsDirty();

                                }}

                              >

                                <div className="toggle-handle" />

                              </div>

                            </div>

                          </div>



                          <div className="form-group">

                            <label>Display Mode</label>

                            <CustomDropdown 

                              id="dropdown-display-mode"

                              value={ccSettings.displayMode}

                              options={["Word by Word", "Line by Line", "Scroll Continuous"]}

                              onChange={(val) => {

                                setCcSettings(prev => ({ ...prev, displayMode: val }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>



                         </div>




                      </motion.div>

                    )}



                    {activeMode === "gif" && (

                      /* SUBPANEL 2: GIF player (GIF) */

                      <motion.div 

                        key="panel-gif"

                        initial={{ opacity: 0, y: 12, filter: "blur(2px)" }}

                        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}

                        exit={{ opacity: 0, y: -12, filter: "blur(2px)" }}

                        transition={{ type: "spring", duration: 0.35, bounce: 0 }}

                        id="panel-gif" 

                        className="settings-panel active"

                      >

                        <div className="form-row">

                          <div className="form-group path-group col-span-2">

                            <label>Load GIF</label>

                            <div className="path-input-wrapper">

                              <input 

                                type="text" 

                                id="input-gif-path" 

                                className="text-input" 

                                readOnly 

                                value={gifSettings.gifPath}

                              />

                              <button 

                                id="btn-browse" 

                                className="btn"

                                onClick={async () => {

                                  const isNative = checkIsNative();

                                  if (isNative && (window as any).pywebview.api.browse_gif) {

                                    const path = await (window as any).pywebview.api.browse_gif();

                                    if (path) {

                                      setGifSettings(prev => ({ ...prev, gifPath: path }));

                                      flagSettingsDirty();

                                    }

                                  } else {

                                    setShowFileModal(true);

                                  }

                                }}

                              >

                                <FolderOpen className="w-4 h-4 mr-2" />

                                Browse

                              </button>

                            </div>

                          </div>



                          <div className="form-group slider-group col-span-2">

                            <label>Threshold</label>

                            <div className="slider-fill-wrapper">

                              <div className="relative w-full flex items-center h-8">

                                <div className="slider-track-background" />

                                <div 

                                  className="slider-track-glow"

                                  style={{ width: `${(gifSettings.threshold / 255) * 100}%` }}

                                />

                                <input 

                                  type="range" 

                                  id="slider-threshold" 

                                  className="slider" 

                                  min="0" 

                                  max="255" 

                                  value={gifSettings.threshold}

                                  onChange={(e) => {

                                    const val = parseInt(e.target.value);

                                    setGifSettings(prev => ({ ...prev, threshold: val }));

                                    flagSettingsDirty();

                                  }}

                                />

                              </div>

                            </div>

                          </div>

                        </div>



                        <div className="form-row">

                          <div className="form-group">

                            <label>Speed</label>

                            <CustomDropdown 

                              id="dropdown-speed"

                              value={gifSettings.speed}

                              options={["1.5 x", "0.5 x", "1.0 x", "2.0 x", "2.5 x", "3.0 x"]}

                              onChange={(val) => {

                                setGifSettings(prev => ({ ...prev, speed: val }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>



                          <div className="form-group">

                            <label>Dithering</label>

                            <CustomDropdown 

                              id="dropdown-dithering"

                              value={gifSettings.dithering}

                              options={["Threshold", "Ordered", "Floyd-Steinberg"]}

                              onChange={(val) => {

                                setGifSettings(prev => ({ ...prev, dithering: val }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>

                        </div>



                        <div className="form-row">

                          <div className="form-group toggle-group">

                            <label>Invert OLED</label>

                            <div className="toggle-container">

                              <div 

                                id="toggle-invert-gif" 

                                className={`toggle-switch ${gifSettings.invertGif ? "on" : ""}`}

                                onClick={() => {

                                  setGifSettings(prev => ({ ...prev, invertGif: !prev.invertGif }));

                                  flagSettingsDirty();

                                }}

                              >

                                <div className="toggle-handle" />

                              </div>

                            </div>

                          </div>



                          <div className="form-group">

                            <label>Sizing Mode</label>

                            <CustomDropdown 

                              id="dropdown-sizing"

                              value={gifSettings.sizingMode}

                              options={["Stretch", "Fit Box", "Center Crop"]}

                              onChange={(val) => {

                                setGifSettings(prev => ({ ...prev, sizingMode: val }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>

                        </div>

                      </motion.div>

                    )}



                    {activeMode === "stats" && (

                      /* SUBPANEL 3: PC monitoring telemetry (Stats) */

                      <motion.div 

                        key="panel-stats"

                        initial={{ opacity: 0, y: 12, filter: "blur(2px)" }}

                        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}

                        exit={{ opacity: 0, y: -12, filter: "blur(2px)" }}

                        transition={{ type: "spring", duration: 0.35, bounce: 0 }}

                        id="panel-stats" 

                        className="settings-panel active"

                      >

                        <div className="form-row">

                          <div className="form-group">

                            <label>Update Interval</label>

                            <CustomDropdown 

                              id="dropdown-interval"

                              value={statsSettings.interval}

                              options={["0.5s", "0.1s", "1.0s", "2.0s"]}

                              onChange={(val) => {

                                setStatsSettings(prev => ({ ...prev, interval: val }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>



                          <div className="form-group">

                            <label>Stats Layout</label>

                            <CustomDropdown 

                              id="dropdown-stats-layout"

                              value={statsSettings.layout}

                              options={["CPU", "GPU", "MEM & NET"]}

                              onChange={(val) => {

                                setStatsSettings(prev => ({ ...prev, layout: val }));

                                flagSettingsDirty();

                              }}

                            />

                          </div>

                        </div>

                        <div className="form-row">
                          <div className="form-group input-group">
                            <label>CPU Min MHz</label>
                            <input 
                              type="number" 
                              id="input-cpu-min-mhz" 
                              className="text-input" 
                              value={statsSettings.cpuMinMhz}
                              onChange={(e) => {
                                const val = parseInt(e.target.value) || 0;
                                setStatsSettings(prev => ({ ...prev, cpuMinMhz: val }));
                                flagSettingsDirty();
                              }}
                            />
                          </div>

                          <div className="form-group input-group">
                            <label>CPU Max MHz</label>
                            <input 
                              type="number" 
                              id="input-cpu-max-mhz" 
                              className="text-input" 
                              value={statsSettings.cpuMaxMhz}
                              onChange={(e) => {
                                const val = parseInt(e.target.value) || 0;
                                setStatsSettings(prev => ({ ...prev, cpuMaxMhz: val }));
                                flagSettingsDirty();
                              }}
                            />
                          </div>
                        </div>

                        <div className="form-row">
                          <div className="form-group input-group">
                            <label>GPU Min Watt</label>
                            <input 
                              type="number" 
                              id="input-gpu-min-watt" 
                              className="text-input" 
                              value={statsSettings.gpuMinWatt}
                              onChange={(e) => {
                                const val = parseInt(e.target.value) || 0;
                                setStatsSettings(prev => ({ ...prev, gpuMinWatt: val }));
                                flagSettingsDirty();
                              }}
                            />
                          </div>

                          <div className="form-group input-group">
                            <label>GPU Max Watt</label>
                            <input 
                              type="number" 
                              id="input-gpu-max-watt" 
                              className="text-input" 
                              value={statsSettings.gpuMaxWatt}
                              onChange={(e) => {
                                const val = parseInt(e.target.value) || 0;
                                setStatsSettings(prev => ({ ...prev, gpuMaxWatt: val }));
                                flagSettingsDirty();
                              }}
                            />
                          </div>
                        </div>

                      </motion.div>

                    )}



                    {activeMode === "clk" && (

                      /* SUBPANEL 4: Clock configuration / info (CLK) */

                      <motion.div 

                        key="panel-clk"

                        initial={{ opacity: 0, y: 12, filter: "blur(2px)" }}

                        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}

                        exit={{ opacity: 0, y: -12, filter: "blur(2px)" }}

                        transition={{ type: "spring", duration: 0.35, bounce: 0 }}

                        id="panel-clk" 

                        className="settings-panel active"

                      >

                        <div className="flex flex-col gap-2 p-4 text-[#e4e4e4] font-['Vin_Mono_Pro_Regular'] text-sm">

                          <div className="form-row">

                            <div className="form-group">

                              <label>Time Format</label>

                              <CustomDropdown 

                                id="dropdown-clock-format"

                                value={clockSettings.clockFormat}

                                options={["12-Hour", "24-Hour"]}

                                onChange={(val) => {

                                  setClockSettings(prev => ({ ...prev, clockFormat: val }));

                                  flagSettingsDirty();

                                }}

                              />

                            </div>

                            <div className="form-group">
                              <label>Clock Theme</label>
                              <CustomDropdown 
                                id="dropdown-clock-theme"
                                value={clockSettings.clockTheme}
                                options={["OBSEDIAN"]}
                                onChange={(val) => {
                                  setClockSettings(prev => ({ ...prev, clockTheme: val }));
                                  flagSettingsDirty();
                                }}
                              />
                            </div>

                          </div>

                        </div>

                      </motion.div>
                    )}
                  </AnimatePresence>

                </div>

              </div>
            </motion.main>

        </AnimatePresence>

      </div>



      {/* Simulated File Broswer Modal (Offline File Selection Experience) */}

      {showFileModal && (

        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[500] font-mono leading-relaxed" style={{ userSelect: "none" }}>

          <div className="bg-[#181818] border border-zinc-800 rounded-2xl w-[600px] p-6 shadow-2xl">

            <h3 className="text-white text-lg font-bold uppercase tracking-wider mb-4 pb-2 border-b border-zinc-800 flex items-center justify-between">

              <span>Choose local GIF file</span>

              <span className="text-xs text-zinc-500">OFFLINE DIRECTORY HOST</span>

            </h3>

            

            <p className="text-zinc-400 text-sm mb-4">

              Select one of the simulated compatible GIF assets available on your local file-system path structure:

            </p>



            <div className="flex flex-col gap-2.5 mb-6">

              {localGifsAvailable.map((path, idx) => (

                <button

                  key={idx}

                  className="w-full text-left bg-zinc-900 border border-zinc-800 hover:border-green-500 hover:bg-zinc-800 text-zinc-300 hover:text-green-400 p-3 rounded-lg text-xs break-all transition-all duration-150 block"

                  onClick={() => handleSelectLocalGif(path)}

                >

                  <span className="text-zinc-500 font-sans mr-2 block text-[10px]">LOCAL DRIVE FILE [{idx + 1}]</span>

                  {path}

                </button>

              ))}

            </div>



            <div className="flex justify-end gap-3 text-sm">

              <button

                className="px-5 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-white rounded-xl transition-all"

                onClick={() => setShowFileModal(false)}

              >

                Cancel

              </button>

            </div>

          </div>

        </div>

      )}

    </div>

  );

}



// Gorgeous High-Fidelity CAD-style Vector Component of the "CAPTOR X" rugged mechanical console

function CaptorXDeviceSVG({ text, isOnline, isRunning }: { text: string; isOnline: boolean; isRunning: boolean }) {

  return (

    <svg viewBox="0 0 560 340" fill="none" className="w-[560px] h-[340px] block select-none">

      {/* Outer black bumper casing with elegant industrial bevel shadows */}

      <rect x="10" y="10" width="540" height="320" rx="28" fill="#101010" stroke="#2a2a2a" strokeWidth="4" />

      <rect x="15" y="15" width="530" height="310" rx="24" fill="#141414" />



      {/* Decorative diagonal cooling ventilation ridges on right grip */}

      <g stroke="#0c0c0c" strokeWidth="6" strokeLinecap="round">

        <line x1="420" y1="80" x2="490" y2="150" />

        <line x1="420" y1="120" x2="490" y2="190" strokeWidth="7" />

        <line x1="420" y1="160" x2="490" y2="230" strokeWidth="8" />

        <line x1="420" y1="200" x2="490" y2="270" strokeWidth="7" />

        <line x1="440" y1="220" x2="490" y2="270" />

      </g>



      {/* Grip shadow boundary */}

      <path d="M 380 40 L 380 300" stroke="#0a0a0a" strokeWidth="2" />

      <path d="M 382 40 L 382 300" stroke="#222222" strokeWidth="1" />



      {/* Four metallic corner socket cap heavy screws with cross drives */}

      <g fill="#2d2d2d" stroke="#121212" strokeWidth="1.5">

        {/* Top Left Screw */}

        <circle cx="36" cy="36" r="14" fill="url(#metalBezel)" />

        <circle cx="36" cy="36" r="8" fill="#1c1c1c" />

        <line x1="32" y1="36" x2="40" y2="36" stroke="#444" strokeWidth="2" />

        <line x1="36" y1="32" x2="36" y2="40" stroke="#444" strokeWidth="2" />



        {/* Top Right Screw */}

        <circle cx="524" cy="36" r="14" fill="url(#metalBezel)" />

        <circle cx="524" cy="36" r="8" fill="#1c1c1c" />

        <line x1="520" y1="36" x2="528" y2="36" stroke="#444" strokeWidth="2" />

        <line x1="524" y1="32" x2="524" y2="40" stroke="#444" strokeWidth="2" />



        {/* Bottom Left Screw */}

        <circle cx="36" cy="304" r="14" fill="url(#metalBezel)" />

        <circle cx="36" cy="304" r="8" fill="#1c1c1c" />

        <line x1="32" y1="304" x2="40" y2="304" stroke="#444" strokeWidth="2" />

        <line x1="36" y1="300" x2="36" y2="308" stroke="#444" strokeWidth="2" />



        {/* Bottom Right Screw */}

        <circle cx="524" cy="304" r="14" fill="url(#metalBezel)" />

        <circle cx="524" cy="304" r="8" fill="#1c1c1c" />

        <line x1="520" y1="304" x2="528" y2="304" stroke="#444" strokeWidth="2" />

        <line x1="524" y1="300" x2="524" y2="308" stroke="#444" strokeWidth="2" />

      </g>



      {/* Embedded decorative grooves along sides */}

      <rect x="70" y="24" width="300" height="4" rx="2" fill="#080808" />

      <rect x="70" y="312" width="300" height="4" rx="2" fill="#080808" />



      {/* Screen metallic glass bezel bezel */}

      <rect x="36" y="104" width="220" height="118" rx="8" fill="#151515" stroke="#333333" strokeWidth="2" />

      <rect x="42" y="110" width="208" height="106" rx="6" fill="#080808" stroke="#1c1c1c" strokeWidth="2" />



      {/* Small textured line indices on physical frame edge */}

      <g stroke="#1a1a1a" strokeWidth="2">

        <line x1="42" y1="230" x2="250" y2="230" />

        <line x1="42" y1="234" x2="250" y2="234" stroke="#0a0a0a" />

      </g>



      {/* Screen Glass Corner Glare shadow */}

      <path d="M 44 112 L 180 112 L 44 212 Z" fill="rgba(255, 255, 255, 0.02)" />



      {/* Status LED node on physical console chassis */}

      <circle cx="280" cy="160" r="4" fill={isOnline ? "#11FF00" : "#FF0038"} filter={isOnline ? "drop-shadow(0 0 3px #11FF00)" : "none"} />



      {/* Physical Decals text stamps */}

      <text x="300" y="164" fill="#777777" fontFamily="monospace" fontSize="10" fontWeight="bold" letterSpacing="0.1em">CAPTOR CORE</text>

      <text x="300" y="180" fill="#444444" fontFamily="monospace" fontSize="8" fontWeight="bold">REV.4.1 [W-N2]</text>



      {/* Gradients definitions packaging */}

      <defs>

        <linearGradient id="metalBezel" x1="0%" y1="0%" x2="100%" y2="100%">

          <stop offset="0%" stopColor="#444444" />

          <stop offset="40%" stopColor="#222222" />

          <stop offset="60%" stopColor="#555555" />

          <stop offset="100%" stopColor="#2c2c2c" />

        </linearGradient>

      </defs>

    </svg>

  );

}

