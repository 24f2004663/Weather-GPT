'use client';

import React, { useState, useEffect, useRef } from 'react';
import { ChatMessage, ChatResponse, LocationResult } from '../types';
import { sendChatMessage, transcribeAudio } from '../lib/api';
import { t, localeTag } from '../lib/translations';
import { Mic, Square, Bot, AlertTriangle, MessageCircle, ArrowUpRight } from 'lucide-react';

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
      content: t('chatWelcomeMessage', currentLanguage),
      source_attribution: ['WeatherGPT Engine'],
    },
  ]);
  const [inputPrompt, setInputPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string>('');
  const [referencedData, setReferencedData] = useState<Record<string, any> | null>(null);
  const [showReferenced, setShowReferenced] = useState(false);

  // Update initial greeting when language changes if no conversation has started yet
  useEffect(() => {
    setMessages((prev) => {
      if (prev.length === 1 && prev[0].role === 'assistant' && !sessionId) {
        return [
          {
            role: 'assistant',
            content: t('chatWelcomeMessage', currentLanguage),
            source_attribution: ['WeatherGPT Engine'],
          },
        ];
      }
      return prev;
    });
  }, [currentLanguage, sessionId]);

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
        content: t('chatWelcomeMessage', currentLanguage),
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
    utterance.lang = localeTag(currentLanguage);
    utterance.rate = 1.0;

    utterance.onend = () => setSpeakingIdx(null);
    utterance.onerror = () => setSpeakingIdx(null);

    setSpeakingIdx(idx);
    window.speechSynthesis.speak(utterance);
  };

  const quickPrompts = [
    selectedLocation ? `${t('quickPromptRain', currentLanguage)} (${selectedLocation.name})` : t('quickPromptRain', currentLanguage),
    selectedLocation ? `${t('quickPromptUmbrella', currentLanguage)} (${selectedLocation.name})` : t('quickPromptUmbrella', currentLanguage),
    selectedLocation ? `${t('quickPromptAlerts', currentLanguage)} (${selectedLocation.name})` : t('quickPromptAlerts', currentLanguage),
    selectedLocation ? `${t('quickPromptClimate', currentLanguage)} (${selectedLocation.name})` : t('quickPromptClimate', currentLanguage),
  ];

  return (
    <div className="w-full glass rounded-3xl p-6 md:p-8 shadow-2xl space-y-6 flex flex-col h-[740px] relative overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/20 pb-3.5">
        <div className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center font-bold text-sm text-white shadow-md shadow-sky-500/20">
            <Bot size={16} strokeWidth={2} aria-hidden="true" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <span>{t('aiAssistant', currentLanguage)}</span>
              {/* Static, not animate-pulse. This sits inside a backdrop-filter pane, so an
                  infinite animation re-rasterizes the whole blurred panel every frame —
                  visible as the panel shimmering, and a constant compositor cost. A ring
                  conveys "online" without animating. */}
              <span
                className="h-2 w-2 rounded-full bg-emerald-400 ring-2 ring-emerald-400/30"
                aria-label={t('aiOnline', currentLanguage)}
                role="img"
              ></span>
            </h3>
            <p className="text-[11px] text-white/70">
              {t('aiSub', currentLanguage)}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2 text-xs">
          {referencedData && (
            <button
              type="button"
              onClick={() => setShowReferenced(!showReferenced)}
              className="px-2.5 py-1 rounded-lg bg-white/10 hover:bg-white/20 text-sky-300 font-mono text-[11px] border border-white/20 transition-colors backdrop-blur-md"
            >
              {showReferenced ? t('hideProvenance', currentLanguage) : t('viewProvenance', currentLanguage)}
            </button>
          )}
          <button
            type="button"
            onClick={handleResetChat}
            className="text-white/70 hover:text-white transition-colors text-xs font-medium"
            title={t('resetConversation', currentLanguage)}
          >
            {t('clearChat', currentLanguage)}
          </button>
        </div>
      </div>

      {/* Provenance Data Viewer Overlay */}
      {showReferenced && referencedData && (
        <div data-surface="dark" className="p-3 bg-black/40 backdrop-blur-2xl border border-white/20 rounded-xl text-xs font-mono text-white/90 max-h-40 overflow-y-auto">
          <div className="font-bold text-sky-400 mb-1">{t('referencedPayload', currentLanguage)}</div>
          <pre className="text-[10px] leading-relaxed whitespace-pre-wrap">{JSON.stringify(referencedData, null, 2)}</pre>
        </div>
      )}

      {/* Voice Error Notification */}
      {voiceError && (
        <div role="alert" className="p-2.5 bg-rose-950/80 border border-rose-800 rounded-xl text-xs text-rose-300 flex justify-between items-center">
          <span className="inline-flex items-center gap-1.5"><AlertTriangle size={13} strokeWidth={2} aria-hidden="true" />{voiceError}</span>
          <button type="button" onClick={() => setVoiceError(null)} className="text-rose-400 font-bold">×</button>
        </div>
      )}

      {/* Message Thread */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1 scrollbar-thin scrollbar-thumb-white/20 scrollbar-track-transparent font-sans text-sm">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-[88%] rounded-2xl px-4 py-3 shadow-md ${
                msg.role === 'user'
                  ? 'bg-sky-600 text-[#fff] rounded-br-none'
                  : 'bg-white/10 backdrop-blur-md text-white border border-white/20 rounded-bl-none'
              }`}
            >
              <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>

              {/* Action Bar for Assistant Messages (Source attribution + TTS Audio Button) */}
              {msg.role === 'assistant' && (
                <div className="mt-2.5 pt-1.5 border-t border-white/10 text-[10px] text-white/60 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 truncate">
                    <span className="text-white/50">{t('sourcesLabel', currentLanguage)}</span>
                    <span className="font-medium text-sky-300 truncate">
                      {msg.source_attribution?.join(' • ') || t('verifiedFeeds', currentLanguage)}
                    </span>
                  </div>

                  {/* Browser TTS Read Aloud Button */}
                  <button
                    type="button"
                    onClick={() => handleToggleSpeak(msg.content, idx)}
                    className="flex-shrink-0 px-2 py-0.5 rounded-md bg-white/10 hover:bg-white/20 text-white/80 font-mono text-[10px] border border-white/20 transition-colors flex items-center gap-1"
                    title={t('readAloudTitle', currentLanguage)}
                  >
                    <span>{speakingIdx === idx ? t('stopListening', currentLanguage) : t('readAloud', currentLanguage)}</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex items-center space-x-2 text-xs text-white/70 bg-white/10 backdrop-blur-md p-3 rounded-2xl max-w-xs border border-white/20">
            <span className="h-2 w-2 rounded-full bg-sky-400 animate-ping"></span>
            <span>{t('queryingWeather', currentLanguage)}</span>
          </div>
        )}

        {isTranscribing && (
          <div className="flex items-center space-x-2 text-xs text-sky-300 bg-white/10 backdrop-blur-md p-3 rounded-2xl max-w-xs border border-sky-400/30">
            <span className="h-2 w-2 rounded-full bg-sky-400 animate-ping"></span>
            <span>{t('transcribingSpeech', currentLanguage)}</span>
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
            className="flex-shrink-0 px-2.5 py-1 rounded-full bg-white/10 hover:bg-white/20 border border-white/20 text-white/80 text-[11px] transition-colors disabled:opacity-50 backdrop-blur-md"
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
          placeholder={isRecording ? t('listeningVoice', currentLanguage) : t('typeMessage', currentLanguage)}
          disabled={isLoading || isRecording}
          className={`w-full bg-white/5 backdrop-blur-md border focus:border-white/40 rounded-2xl px-4 py-2.5 pr-28 text-sm text-white placeholder-white/50 focus:outline-none resize-none transition-colors ${
            isRecording ? 'border-rose-500 bg-rose-950/40 animate-pulse' : 'border-white/20'
          }`}
          aria-label={t('aiAssistant', currentLanguage)}
        />

        <div className="absolute right-3 bottom-5 flex items-center space-x-2">
          {/* Microphone Button */}
          <button
            type="button"
            onClick={isRecording ? handleStopRecording : handleStartRecording}
            disabled={isLoading || isTranscribing}
            className={`h-7 w-7 rounded-xl flex items-center justify-center text-xs font-medium transition-all ${
              isRecording
                ? 'bg-rose-600 text-[#fff] animate-bounce shadow-lg shadow-rose-600/30'
                : 'bg-white/10 hover:bg-white/20 text-white/80 border border-white/20 backdrop-blur-md'
            }`}
            title={isRecording ? t('stopRecording', currentLanguage) : t('voiceInput', currentLanguage)}
            aria-label={isRecording ? t('stopRecording', currentLanguage) : t('voiceInput', currentLanguage)}
            aria-pressed={isRecording}
          >
            {/* The glyph is decorative; the accessible name comes from aria-label above,
                otherwise a screen reader announces the raw emoji or nothing at all. */}
            {isRecording
              ? <Square size={13} strokeWidth={2.5} fill="currentColor" aria-hidden="true" />
              : <Mic size={14} strokeWidth={2} aria-hidden="true" />}
          </button>

          {/* Send Button */}
          <button
            type="button"
            onClick={() => handleSend()}
            disabled={isLoading || isRecording || !inputPrompt.trim()}
            className="bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-[#fff] font-semibold px-3.5 py-1.5 rounded-xl text-xs transition-all shadow-lg shadow-sky-600/20"
          >
            {t('send', currentLanguage)}
          </button>
        </div>
      </div>

      {/* WhatsApp Chatbot CTA Card */}
      <div className="pt-1">
        <div className="glass-inset hover:border-white/20 rounded-2xl p-3 transition-colors shadow-md flex items-center justify-between gap-3">
          <div className="flex items-center space-x-2.5 min-w-0">
            <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-600 flex items-center justify-center text-sm text-white shadow-md shadow-emerald-500/20 flex-shrink-0">
              <MessageCircle size={16} strokeWidth={2} aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <div className="text-xs font-bold text-white flex items-center gap-1.5 truncate">
                <span>{t('tryWhatsAppChatbot', currentLanguage)}</span>
                {isAlertSubscribed ? (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                    {t('activeStatus', currentLanguage)}
                  </span>
                ) : (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-amber-950/80 text-amber-300 border border-amber-800">
                    {t('alertsRequired', currentLanguage)}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-white/70 truncate">
                {t('chatWithWhatsAppDesc', currentLanguage)}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleWhatsAppClick}
            className="flex-shrink-0 px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-[#fff] font-semibold text-xs transition-all shadow-md shadow-emerald-600/20 flex items-center gap-1"
          >
            <span>{t('tryWhatsAppButton', currentLanguage)}</span>
            <ArrowUpRight size={12} strokeWidth={2.5} aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}
