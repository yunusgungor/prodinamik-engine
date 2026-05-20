/**
 * PipelineVisualizer — Prodinamik Engine pipeline görsel akış bileşeni.
 * 
 * Her profil için full state machine akışını yatay bir pipeline olarak
 * gösterir. Mevcut state vurgulu, state tipleri renk kodlu.
 */

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { CheckCircle2, Circle, Clock, AlertTriangle, Play } from "lucide-react";

// ── Profile Pipeline Definitions ──

interface PipelineState {
  name: string;
  type: "initial" | "intermediate" | "pause" | "terminal";
  description?: string;
}

interface PipelineDefinition {
  id: string;
  name: string;
  states: PipelineState[];
}

export const PIPELINE_DEFINITIONS: Record<string, PipelineDefinition> = {
  software: {
    id: "software",
    name: "Software Pipeline",
    states: [
      { name: "spec", type: "initial", description: "Proje tanımı ve gereksinimler" },
      { name: "prototyping", type: "intermediate", description: "Hızlı prototip oluşturma" },
      { name: "iteration", type: "intermediate", description: "Iteratif geliştirme (self-loop)" },
      { name: "review", type: "pause", description: "İnsan onayı bekliyor" },
      { name: "release", type: "terminal", description: "Yayınlandı" },
    ],
  },
  content: {
    id: "content",
    name: "Content Pipeline",
    states: [
      { name: "captured", type: "initial", description: "Fikir yakalandı" },
      { name: "decide_route", type: "intermediate", description: "Kanal seçimi" },
      { name: "idea_review", type: "intermediate", description: "Fikir değerlendirmesi" },
      { name: "brief_ready", type: "intermediate", description: "Brief hazır" },
      { name: "drafting", type: "intermediate", description: "Taslak oluşturma" },
      { name: "verification", type: "intermediate", description: "Doğrulama" },
      { name: "draft_review", type: "pause", description: "✋ İnsan onayı bekliyor" },
      { name: "approved", type: "intermediate", description: "Onaylandı" },
      { name: "published", type: "pause", description: "Yayınlandı" },
      { name: "archived", type: "terminal", description: "Arşivlendi" },
    ],
  },
  haber: {
    id: "haber",
    name: "News Pipeline",
    states: [
      { name: "captured", type: "initial", description: "Haber kaynağı yakalandı" },
      { name: "fact_checking", type: "intermediate", description: "Doğruluk kontrolü" },
      { name: "cross_verified", type: "intermediate", description: "Çapraz doğrulama" },
      { name: "published", type: "pause", description: "✋ Yayın onayı" },
      { name: "correction_needed", type: "pause", description: "✋ Düzeltme gerekli" },
    ],
  },
  devcycle: {
    id: "devcycle",
    name: "DevCycle Pipeline",
    states: [
      { name: "brief", type: "initial", description: "Görev tanımı" },
      { name: "prototyping", type: "intermediate", description: "Hızlı prototip" },
      { name: "development", type: "intermediate", description: "Geliştirme" },
      { name: "drift_resolution", type: "intermediate", description: "Drift çözümü" },
      { name: "review", type: "pause", description: "✋ İnceleme onayı" },
      { name: "blocked", type: "pause", description: "✋ Engellendi" },
    ],
  },
  research: {
    id: "research",
    name: "Research Pipeline",
    states: [
      { name: "topic_selected", type: "initial", description: "Konu seçildi" },
      { name: "literature_review", type: "intermediate", description: "Literatür taraması" },
      { name: "hypothesis", type: "intermediate", description: "Hipotez oluşturma" },
      { name: "experiment_design", type: "intermediate", description: "Deney tasarımı" },
      { name: "paper_draft", type: "intermediate", description: "Makale taslağı" },
      { name: "peer_review", type: "pause", description: "✋ Akran değerlendirmesi" },
    ],
  },
  design: {
    id: "design",
    name: "Design Pipeline",
    states: [
      { name: "brief", type: "initial", description: "Tasarım brief'i" },
      { name: "research", type: "intermediate", description: "Araştırma" },
      { name: "sketch", type: "intermediate", description: "Eskiz" },
      { name: "wireframe", type: "intermediate", description: "Tel kafes" },
      { name: "mockup", type: "intermediate", description: "Maket" },
      { name: "prototype", type: "intermediate", description: "Prototip" },
      { name: "review", type: "pause", description: "✋ Tasarım onayı" },
    ],
  },
};

// ── Style Configuration ──

const STATE_STYLES: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  initial: { bg: "bg-emerald-500/15", border: "border-emerald-500/40", text: "text-emerald-400", icon: "text-emerald-400" },
  intermediate: { bg: "bg-blue-500/10", border: "border-blue-500/30", text: "text-blue-400", icon: "text-blue-400" },
  pause: { bg: "bg-amber-500/15", border: "border-amber-500/40", text: "text-amber-400", icon: "text-amber-400" },
  terminal: { bg: "bg-slate-500/10", border: "border-slate-500/30", text: "text-slate-400", icon: "text-slate-400" },
};

const STATE_GLOW: Record<string, string> = {
  initial: "shadow-emerald-500/25",
  intermediate: "shadow-blue-500/20",
  pause: "shadow-amber-500/25",
  terminal: "shadow-slate-500/20",
};

// ── Component ──

interface PipelineVisualizerProps {
  profile: string;
  currentState?: string;
  onChangeState?: (state: string) => void;
  compact?: boolean;
  className?: string;
}

export function PipelineVisualizer({
  profile,
  currentState,
  onChangeState,
  compact = false,
  className,
}: PipelineVisualizerProps) {
  const pipeline = PIPELINE_DEFINITIONS[profile];
  const states = pipeline?.states ?? [];

  const currentIndex = useMemo(
    () => states.findIndex((s) => s.name === currentState),
    [states, currentState]
  );

  if (!pipeline || states.length === 0) {
    return (
      <div className="text-xs text-muted-foreground text-center py-4">
        Unknown profile: "{profile}"
      </div>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      {/* Pipeline label */}
      {!compact && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
          <span className="font-medium">{pipeline.name}</span>
          <span className="text-muted-foreground/50">·</span>
          <span>{states.length} states</span>
          {currentIndex >= 0 && (
            <>
              <span className="text-muted-foreground/50">·</span>
              <span className="text-primary font-mono">
                Step {currentIndex + 1} of {states.length}
              </span>
            </>
          )}
        </div>
      )}

      {/* Pipeline horizontal flow */}
      <div className="flex items-start gap-0 overflow-x-auto pb-2">
        {states.map((state, i) => {
          const style = STATE_STYLES[state.type] ?? STATE_STYLES.intermediate;
          const isCurrent = state.name === currentState;
          const isPast = currentIndex >= 0 && i < currentIndex;
          const isFuture = currentIndex >= 0 && i > currentIndex;

          return (
            <div key={state.name} className="flex items-center shrink-0">
              {/* State node */}
              <button
                onClick={() => onChangeState?.(state.name)}
                className={cn(
                  "flex flex-col items-center gap-1 px-3 py-2 rounded-lg border transition-all duration-200 min-w-[90px]",
                  style.bg,
                  style.border,
                  isCurrent && [
                    "ring-2 ring-offset-2 ring-offset-background scale-105 z-10",
                    STATE_GLOW[state.type],
                    state.type === "pause" ? "ring-amber-400 shadow-lg" : "ring-primary",
                  ],
                  isPast && "opacity-60",
                  isFuture && "opacity-50",
                  onChangeState && "cursor-pointer hover:scale-105",
                  !onChangeState && "cursor-default"
                )}
                data-testid={`pipeline-state-${state.name}`}
                title={state.description}
              >
                {/* State icon */}
                <div className={cn(
                  "w-6 h-6 rounded-full flex items-center justify-center",
                  isCurrent ? cn("bg-foreground/10", style.text) : "text-muted-foreground/60"
                )}>
                  {isCurrent ? (
                    state.type === "pause" ? (
                      <Clock className="w-3.5 h-3.5 animate-pulse" />
                    ) : (
                      <Play className="w-3 h-3" />
                    )
                  ) : isPast ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : (
                    <Circle className="w-3 h-3" />
                  )}
                </div>

                {/* State name */}
                <span className={cn(
                  "text-[10px] font-mono font-medium leading-tight text-center",
                  isCurrent ? style.text : "text-muted-foreground/80"
                )}>
                  {state.name.replace(/_/g, " ")}
                </span>

                {/* PAUSE badge */}
                {state.type === "pause" && (
                  <span className="text-[8px] text-amber-400/80 font-medium mt-0.5">⏸ PAUSE</span>
                )}

                {/* Current indicator */}
                {isCurrent && (
                  <span className="text-[8px] text-primary font-semibold mt-0.5">● CURRENT</span>
                )}
              </button>

              {/* Connector arrow */}
              {i < states.length - 1 && (
                <div className={cn(
                  "flex items-center mx-1",
                  isPast ? "text-muted-foreground/40" : "text-muted-foreground/20"
                )}>
                  <svg width="20" height="2" viewBox="0 0 20 2" className="fill-current">
                    <line x1="0" y1="1" x2="16" y2="1" stroke="currentColor" strokeWidth="1.5" />
                    <polygon points="16,0 20,1 16,2" fill="currentColor" />
                  </svg>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Legend (compact mode) */}
      {compact && (
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-emerald-500/60" />
            <span>Initial</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-blue-500/60" />
            <span>Step</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-amber-500/60" />
            <span>PAUSE</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-slate-500/60" />
            <span>Terminal</span>
          </div>
        </div>
      )}

      {/* Current state description */}
      {!compact && currentState && states[currentIndex] && (
        <div className={cn(
          "text-xs px-3 py-1.5 rounded-md border",
          STATE_STYLES[states[currentIndex].type]?.bg,
          STATE_STYLES[states[currentIndex].type]?.border
        )}>
          <span className="font-medium font-mono">{currentState}:</span>{" "}
          <span className="text-muted-foreground">{states[currentIndex].description}</span>
          {currentIndex < states.length - 1 && (
            <span className="text-muted-foreground/60 ml-1">
              → Next: <span className="font-mono">{states[currentIndex + 1].name}</span>
            </span>
          )}
          {currentIndex === states.length - 1 && (
            <span className="text-muted-foreground/60 ml-1">✓ Pipeline complete</span>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * PipelineProgress — kompakt ilerleme çubuğu.
 * Run detail sayfasının üst kısmında kullanılır.
 */
export function PipelineProgress({
  profile,
  currentState,
  className,
}: {
  profile: string;
  currentState?: string;
  className?: string;
}) {
  const pipeline = PIPELINE_DEFINITIONS[profile];
  const states = pipeline?.states ?? [];
  const currentIndex = states.findIndex((s) => s.name === currentState);
  const progress = states.length > 0 ? ((currentIndex + 1) / states.length) * 100 : 0;

  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span className="font-medium">{pipeline?.name ?? profile}</span>
        <span className="font-mono">
          {currentIndex >= 0 ? `${currentIndex + 1}/${states.length}` : "—"}
        </span>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            currentIndex >= states.length - 1 ? "bg-emerald-500" : "bg-primary"
          )}
          style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
        />
      </div>
      {currentIndex >= 0 && currentIndex < states.length - 1 && (
        <p className="text-[10px] text-muted-foreground">
          Next: <span className="font-mono text-primary">{states[currentIndex + 1]?.name}</span>
        </p>
      )}
    </div>
  );
}
