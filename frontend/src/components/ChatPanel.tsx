'use client';

import React, { useState, useEffect, useRef } from 'react';
import { ChatMessage, ChatResponse, LocationResult } from '../types';
import { sendChatMessage, transcribeAudio } from '../lib/api';

interface ChatPanelProps {
  selectedLocation: LocationResult | null;
  currentLanguage?: string;
  isAlertSubscribed?: boolean;
  onOpenNotificationSettings?: () => void;
}

export default function ChatPanel({
  selectedLocation,
  currentLanguage = 'en',
  isAlertSubscribed = false,
  onOpenNotificationSettings,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content:
        "Hello! I am WeatherGPT, your AI weather intelligence assistant. Ask me anything about current conditions, rain forecasts, travel weather, disaster warnings, or long-term climate baselines.",
      source_attribution: ['WeatherGPT Engine'],
    },
  ]);
  const [inputPrompt, setInputPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string>('');
  const [referencedData, setReferencedData] = useState<Record<string, any> | null>(null);
  const [showReferenced, setShowReferenced] = useState(false);

  const handleWhatsAppClick = () => {
    if (isAlertSubscribed) {
      if (typeof window !== 'undefined') {
        window.open('https://wa.me/919042099020?text=Hi%20WeatherGPT', '_blank', 'noopener,noreferrer');
      }
    } else {
      onOpenNotificationSettings?.();
    }
  };

  // Voice STT State
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Browser TTS State
  const [speakingIdx, setSpeakingIdx] = useState<number | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom of conversation
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading, isTranscribing]);

  // Clean up speech on unmount
  useEffect(() => {
    return () => {
      if (typeof window !== 'undefined' && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const getSupportedAudioMime = (): { mimeType: string; extension: string } => {
    if (typeof window !== 'undefined' && typeof MediaRecorder !== 'undefined') {
      const candidates = [
        { mimeType: 'audio/webm;codecs=opus', extension: 'webm' },
        { mimeType: 'audio/webm', extension: 'webm' },
        { mimeType: 'audio/mp4', extension: 'mp4' },
        { mimeType: 'audio/aac', extension: 'aac' },
        { mimeType: 'audio/ogg', extension: 'ogg' },
      ];
      for (const cand of candidates) {
        if (MediaRecorder.isTypeSupported(cand.mimeType)) {
          return cand;
        }
      }
    }
    return { mimeType: 'audio/webm', extension: 'webm' };
  };

  const handleSend = async (promptToSend?: string) => {
    const text = promptToSend || inputPrompt;
    if (!text.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      role: 'user',
      content: text.trim(),
      timestamp: new Date().toISOString(),
    };

    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);
    setInputPrompt('');
    setIsLoading(true);

    try {
      // Send bounded recent context (last 6 messages). If backend session is active,
      // backend will use server-side session history; if backend restarted/expired,
      // this bounded context provides immediate conversational continuity without unbounded payload growth.
      const payloadMessages = updatedMessages.slice(-6);

      const res: ChatResponse = await sendChatMessage({
        messages: payloadMessages,
        user_location: selectedLocation?.name,
        coordinates: selectedLocation
          ? { latitude: selectedLocation.latitude, longitude: selectedLocation.longitude }
          : undefined,
        language_preference: currentLanguage,
        session_id: sessionId || undefined,
      });

      setSessionId(res.session_id);
      if (res.referenced_weather_data) {
        setReferencedData(res.referenced_weather_data);
      }
      setMessages([...updatedMessages, res.response_message]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: `Error: ${err.message || 'Unable to connect to WeatherGPT AI Engine. Please check your connection and configuration.'}`,
        source_attribution: ['System Error'],
        timestamp: new Date().toISOString(),
      };
      setMessages([...updatedMessages, errorMsg]);
    } finally {
      setIsLoading(false);
      textareaRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleResetChat = () => {
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel();
      setSpeakingIdx(null);
    }
    setMessages([
      {
        role: 'assistant',
        content:
          "Conversation reset. How can I assist you with weather intelligence today?",
        source_attribution: ['WeatherGPT Engine'],
      },
    ]);
    setSessionId('');
    setReferencedData(null);
  };

  // --- Voice Input (STT via Backend Groq Whisper with Safari/iOS MIME compatibility) ---
  const handleStartRecording = async () => {
    setVoiceError(null);
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setVoiceError('Microphone not supported on this browser.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      
      const { mimeType } = getSupportedAudioMime();
      const options = mimeType ? { mimeType } : undefined;
      const mediaRecorder = options ? new MediaRecorder(stream, options) : new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const chosen = getSupportedAudioMime();
        const audioBlob = new Blob(audioChunksRef.current, { type: chosen.mimeType || 'audio/webm' });
        await handleTranscribeBlob(audioBlob, chosen.extension);
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err: any) {
      setVoiceError('Microphone permission denied or audio device unavailable.');
    }
  };

  const handleStopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleTranscribeBlob = async (blob: Blob, ext: string = 'webm') => {
    setIsTranscribing(true);
    setVoiceError(null);
    try {
      const formData = new FormData();
      formData.append('file', blob, `recording.${ext}`);
      formData.append('language', currentLanguage);

      const data = await transcribeAudio(formData);
      if (data.transcription) {
        setInputPrompt((prev) => (prev ? `${prev} ${data.transcription}` : data.transcription));
      }
    } catch (err: any) {
      setVoiceError(err.message || 'Voice transcription failed.');
    } finally {
      setIsTranscribing(false);
    }
  };

  // --- Browser SpeechSynthesis (TTS Fallback) ---
  const handleToggleSpeak = (text: string, idx: number) => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return;

    if (speakingIdx === idx) {
      window.speechSynthesis.cancel();
      setSpeakingIdx(null);
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);

    // Language code mapping
    const langMap: Record<string, string> = {
      en: 'en-IN',
      hi: 'hi-IN',
      ta: 'ta-IN',
      te: 'te-IN',
      bn: 'bn-IN',
    };
    utterance.lang = langMap[currentLanguage] || 'en-US';
    utterance.rate = 1.0;

    utterance.onend = () => setSpeakingIdx(null);
    utterance.onerror = () => setSpeakingIdx(null);

    setSpeakingIdx(idx);
    window.speechSynthesis.speak(utterance);
  };

  const quickPrompts = [
    selectedLocation ? `Will it rain today in ${selectedLocation.name}?` : 'Will it rain today?',
    selectedLocation ? `Should I carry an umbrella in ${selectedLocation.name}?` : 'Should I carry an umbrella?',
    selectedLocation ? `Are there any active disaster warnings for ${selectedLocation.name}?` : 'Active disaster alerts',
    selectedLocation ? `What is the 30-year climate baseline for ${selectedLocation.name}?` : 'Historical climate baseline',
  ];

  return (
    <div className="w-full bg-slate-900/90 border border-slate-800 rounded-3xl p-6 md:p-8 shadow-2xl space-y-6 flex flex-col h-[740px] relative overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3.5">
        <div className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center font-bold text-sm text-white shadow-md shadow-sky-500/20">
            🤖
          </div>
          <div>
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <span>WeatherGPT Intelligence Assistant</span>
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Grounded in Open-Meteo, NASA POWER, and SACHET/NDMA
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2 text-xs">
          {referencedData && (
            <button
              type="button"
              onClick={() => setShowReferenced(!showReferenced)}
              className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-300 font-mono text-[11px] border border-slate-700 transition-colors"
            >
              {showReferenced ? 'Hide Provenance' : 'View Provenance'}
            </button>
          )}
          <button
            type="button"
            onClick={handleResetChat}
            className="text-slate-400 hover:text-slate-200 transition-colors text-xs font-medium"
            title="Reset conversation"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Provenance Data Viewer Overlay */}
      {showReferenced && referencedData && (
        <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl text-xs font-mono text-slate-300 max-h-40 overflow-y-auto">
          <div className="font-bold text-sky-400 mb-1">Referenced Structured Meteorological Payload:</div>
          <pre className="text-[10px] leading-relaxed whitespace-pre-wrap">{JSON.stringify(referencedData, null, 2)}</pre>
        </div>
      )}

      {/* Voice Error Notification */}
      {voiceError && (
        <div className="p-2.5 bg-rose-950/80 border border-rose-800 rounded-xl text-xs text-rose-300 flex justify-between items-center">
          <span>⚠️ {voiceError}</span>
          <button type="button" onClick={() => setVoiceError(null)} className="text-rose-400 font-bold">×</button>
        </div>
      )}

      {/* Message Thread */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-900 font-sans text-sm">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-[88%] rounded-2xl px-4 py-3 shadow-md ${
                msg.role === 'user'
                  ? 'bg-sky-600 text-white rounded-br-none'
                  : 'bg-slate-950/80 text-slate-200 border border-slate-800/90 rounded-bl-none'
              }`}
            >
              <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>

              {/* Action Bar for Assistant Messages (Source attribution + TTS Audio Button) */}
              {msg.role === 'assistant' && (
                <div className="mt-2.5 pt-1.5 border-t border-slate-800/60 text-[10px] text-slate-400 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 truncate">
                    <span className="text-slate-500">Sources:</span>
                    <span className="font-medium text-sky-300 truncate">
                      {msg.source_attribution?.join(' • ') || 'Verified Feeds'}
                    </span>
                  </div>

                  {/* Browser TTS Read Aloud Button */}
                  <button
                    type="button"
                    onClick={() => handleToggleSpeak(msg.content, idx)}
                    className="flex-shrink-0 px-2 py-0.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono text-[10px] border border-slate-700 transition-colors flex items-center gap-1"
                    title="Read response aloud"
                  >
                    <span>{speakingIdx === idx ? '⏹️ Stop' : '🔊 Listen'}</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex items-center space-x-2 text-xs text-slate-400 bg-slate-950/50 p-3 rounded-2xl max-w-xs border border-slate-800/80">
            <span className="h-2 w-2 rounded-full bg-sky-400 animate-ping"></span>
            <span>Querying weather feeds and analyzing...</span>
          </div>
        )}

        {isTranscribing && (
          <div className="flex items-center space-x-2 text-xs text-sky-300 bg-slate-950/50 p-3 rounded-2xl max-w-xs border border-sky-800/80">
            <span className="h-2 w-2 rounded-full bg-sky-400 animate-ping"></span>
            <span>Transcribing speech with Groq Whisper...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Quick Suggestion Chips */}
      <div className="flex gap-2 overflow-x-auto pb-1 text-xs">
        {quickPrompts.map((chip, i) => (
          <button
            key={i}
            type="button"
            onClick={() => handleSend(chip)}
            disabled={isLoading || isRecording || isTranscribing}
            className="flex-shrink-0 px-2.5 py-1 rounded-full bg-slate-950/80 hover:bg-slate-800 border border-slate-800 text-slate-300 text-[11px] transition-colors disabled:opacity-50"
          >
            {chip}
          </button>
        ))}
      </div>

      {/* Input Composer & Voice Mic Button */}
      <div className="relative pt-2">
        <textarea
          ref={textareaRef}
          rows={2}
          value={inputPrompt}
          onChange={(e) => setInputPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isRecording ? 'Listening to your voice...' : 'Ask a weather question or tap the mic...'}
          disabled={isLoading || isRecording}
          className={`w-full bg-slate-950 border focus:border-sky-500 rounded-2xl px-4 py-2.5 pr-28 text-sm text-white placeholder-slate-500 focus:outline-none resize-none transition-colors ${
            isRecording ? 'border-rose-500 bg-rose-950/20 animate-pulse' : 'border-slate-800'
          }`}
          aria-label="Message WeatherGPT"
        />

        <div className="absolute right-3 bottom-5 flex items-center space-x-2">
          {/* Microphone Button */}
          <button
            type="button"
            onClick={isRecording ? handleStopRecording : handleStartRecording}
            disabled={isLoading || isTranscribing}
            className={`h-7 w-7 rounded-xl flex items-center justify-center text-xs font-medium transition-all ${
              isRecording
                ? 'bg-rose-600 text-white animate-bounce shadow-lg shadow-rose-600/30'
                : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700'
            }`}
            title={isRecording ? 'Stop recording' : 'Voice input (Groq Whisper)'}
          >
            <span>{isRecording ? '⏹️' : '🎙️'}</span>
          </button>

          {/* Send Button */}
          <button
            type="button"
            onClick={() => handleSend()}
            disabled={isLoading || isRecording || !inputPrompt.trim()}
            className="bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white font-semibold px-3.5 py-1.5 rounded-xl text-xs transition-all shadow-lg shadow-sky-600/20"
          >
            Send
          </button>
        </div>
      </div>

      {/* WhatsApp Chatbot CTA Card */}
      <div className="pt-1">
        <div className="bg-slate-950/80 border border-slate-800/90 hover:border-emerald-500/40 rounded-2xl p-3 transition-all shadow-md flex items-center justify-between gap-3">
          <div className="flex items-center space-x-2.5 min-w-0">
            <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-600 flex items-center justify-center text-sm text-white shadow-md shadow-emerald-500/20 flex-shrink-0">
              💬
            </div>
            <div className="min-w-0">
              <div className="text-xs font-bold text-white flex items-center gap-1.5 truncate">
                <span>Try our WhatsApp Chatbot</span>
                {isAlertSubscribed ? (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                    Active
                  </span>
                ) : (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-amber-950/80 text-amber-300 border border-amber-800">
                    Alerts Required
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-400 truncate">
                Chat with WeatherGPT on WhatsApp
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleWhatsAppClick}
            className="flex-shrink-0 px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-semibold text-xs transition-all shadow-md shadow-emerald-600/20 flex items-center gap-1"
          >
            <span>Try WhatsApp</span>
            <span className="text-[10px]">↗</span>
          </button>
        </div>
      </div>
    </div>
  );
}
