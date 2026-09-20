import { useEffect, useRef, useState } from 'react';
import { useAppStore } from '../lib/store';
import { fetchManagedAgents, sendChatMessage, synthesizeSpeech } from '../lib/api';
import { useSpeech } from '../hooks/useSpeech';

type PulseState = 'idle' | 'inferencing' | 'speaking' | 'agent-active';

export function OrbePage() {
  const isStreaming = useAppStore((s) => s.streamState.isStreaming);
  const [hasRunningAgent, setHasRunningAgent] = useState(false);
  const [orbState, setOrbState] = useState<PulseState>('idle');
  const [lastResponse, setLastResponse] = useState<string | null>(null);
  const [responseError, setResponseError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const { state: speechState, error: speechError, available, startRecording, stopRecording } = useSpeech();

  useEffect(() => {
    const check = () =>
      fetchManagedAgents()
        .then((agents) => setHasRunningAgent(agents.some((a) => a.status === 'running')))
        .catch(() => {});
    check();
    const interval = setInterval(check, 10000);
    return () => clearInterval(interval);
  }, []);

  // Sync orbState with speechState and external streaming state
  useEffect(() => {
    if (orbState === 'speaking') return; // don't interrupt playback
    if (speechState === 'transcribing' || isStreaming) {
      setOrbState('inferencing');
    } else if (hasRunningAgent) {
      setOrbState('agent-active');
    } else if (speechState === 'idle') {
      setOrbState('idle');
    }
  }, [speechState, isStreaming, hasRunningAgent, orbState]);

  const pulseColors: Record<PulseState, string> = {
    idle: 'bg-blue-500/20 shadow-blue-500/50',
    inferencing: 'bg-purple-500/80 shadow-purple-500/80 animate-pulse',
    speaking: 'bg-cyan-400/80 shadow-cyan-400/80 animate-pulse',
    'agent-active': 'bg-green-500/80 shadow-green-500/80 animate-bounce',
  };

  const orbLabel = (): string => {
    if (speechState === 'recording') return 'LISTENING';
    if (orbState === 'inferencing' || speechState === 'transcribing') return 'THINKING';
    if (orbState === 'speaking') return 'SPEAKING';
    if (orbState === 'agent-active') return 'ACTIVE';
    return 'CERBERUS';
  };

  const handleTranscriptReady = async (text: string) => {
    setResponseError(null);
    setOrbState('inferencing');

    let responseText = '';
    try {
      const { content } = await sendChatMessage(text);
      responseText = content;
      setLastResponse(content);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setResponseError(`Erreur agent: ${msg}`);
      setOrbState('idle');
      return;
    }

    // Attempt TTS playback — gracefully degrade if TTS unavailable
    const audioBlob = responseText ? await synthesizeSpeech(responseText) : null;

    if (audioBlob) {
      const url = URL.createObjectURL(audioBlob);
      const audio = new Audio(url);
      audioRef.current = audio;
      setOrbState('speaking');
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setOrbState('idle');
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        setOrbState('idle');
      };
      audio.play().catch(() => setOrbState('idle'));
    } else {
      // TTS not configured — still show the text response
      setOrbState('idle');
    }
  };

  const handleOrbClick = async () => {
    if (orbState === 'speaking') {
      // Stop ongoing playback
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      setOrbState('idle');
      return;
    }
    if (speechState === 'idle') {
      setResponseError(null);
      await startRecording();
    } else if (speechState === 'recording') {
      try {
        const text = await stopRecording();
        if (text) {
          await handleTranscriptReady(text);
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setResponseError(msg);
        setOrbState('idle');
      }
    }
  };

  const currentPulse = pulseColors[orbState];

  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-screen relative overflow-hidden bg-black/5">
      {/* Main Orb */}
      <div
        id="cerberus-orb"
        onClick={handleOrbClick}
        className={`w-64 h-64 rounded-full shadow-[0_0_80px] transition-all duration-700 cursor-pointer flex items-center justify-center ${currentPulse} ${speechState === 'recording' ? 'scale-125 ring-8 ring-red-500/50' : 'hover:scale-105'}`}
      >
        <div className="text-white/80 font-bold tracking-widest select-none drop-shadow-md text-sm">
          {orbLabel()}
        </div>
      </div>

      {/* Hint text */}
      <p className="mt-6 text-white/30 text-xs tracking-widest select-none">
        {speechState === 'recording'
          ? 'Cliquez pour envoyer'
          : orbState === 'speaking'
          ? 'Cliquez pour interrompre'
          : 'Cliquez pour parler'}
      </p>

      {/* Agent response text */}
      {lastResponse && orbState !== 'speaking' && (
        <div className="absolute bottom-24 max-w-md mx-auto text-center text-white/60 text-sm bg-white/5 rounded-xl px-6 py-4 backdrop-blur-sm">
          {lastResponse}
        </div>
      )}

      {/* Speech backend unavailable warning */}
      {!available && (
        <div className="absolute top-10 text-yellow-500 bg-yellow-500/10 px-4 py-2 rounded text-sm">
          Speech backend non disponible
        </div>
      )}

      {/* Error banner */}
      {(speechError || responseError) && (
        <div className="absolute bottom-10 text-red-400 bg-red-500/10 px-4 py-2 rounded text-sm max-w-sm text-center">
          {speechError || responseError}
        </div>
      )}
    </div>
  );
}
