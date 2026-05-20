/**
 * HITLDialog — Human-In-The-Loop PAUSE state yönetimi.
 * 
 * Run PAUSE state'teyken kullanıcıya soruları gösterir,
 * cevapları engine'e iletir, resume işlemini yapar.
 */

import { useState, useEffect, useCallback } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { AlertCircle, Clock, Send, CheckCircle2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

interface HITLQuestion {
  question: string;
  type: "yes_no" | "multiple_choice";
  choices?: string[];
  timeout?: number;
}

interface HITLDialogProps {
  open: boolean;
  onClose: () => void;
  slug: string;
  state: string;
  questions: HITLQuestion[];
  timeout?: number;
  onResolved?: () => void;
}

export function HITLDialog({
  open,
  onClose,
  slug,
  state,
  questions,
  timeout,
  onResolved,
}: HITLDialogProps) {
  const { toast } = useToast();
  const [currentQ, setCurrentQ] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [countdown, setCountdown] = useState(timeout ?? 0);
  const [resolved, setResolved] = useState(false);

  // Timeout countdown
  useEffect(() => {
    if (!timeout || timeout <= 0 || resolved) return;
    setCountdown(timeout);
    const interval = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [timeout, resolved]);

  const question = questions[currentQ];
  const isLast = currentQ >= questions.length - 1;

  const handleAnswer = (answer: string) => {
    setAnswers((prev) => ({ ...prev, [currentQ]: answer }));
  };

  const handleNext = () => {
    if (currentQ < questions.length - 1) {
      setCurrentQ((prev) => prev + 1);
    }
  };

  const handleSubmit = async () => {
    if (submitting) return;
    setSubmitting(true);

    try {
      const stored = localStorage.getItem("pdmk-auth");
      const parsed = stored ? JSON.parse(stored) : null;
      const apiBase = parsed?.state?.baseUrl || "http://localhost:8000";
      const apiKey = parsed?.state?.apiKey || "";
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
      };

      // Collect all answers
      const combinedAnswer = answers[0] || "";
      const body = {
        answers: {
          answer: combinedAnswer,
          feedback: feedback || undefined,
        },
      };

      const res = await fetch(`${apiBase}/api/v1/runs/${slug}/resume`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });

      if (res.ok) {
        const result = await res.json();
        toast({
          title: "✅ Resume successful",
          description: `Run transitioned to: ${result.state || "next state"}`,
        });
        setResolved(true);
        onResolved?.();
        onClose();
      } else {
        const err = await res.json().catch(() => ({}));
        toast({
          title: "❌ Resume failed",
          description: err.detail || "Unknown error",
          variant: "destructive",
        });
      }
    } catch (e: any) {
      toast({
        title: "❌ Connection error",
        description: e.message || "Could not reach engine",
        variant: "destructive",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleQuickResume = async (answer: string) => {
    setAnswers({ 0: answer });
    setFeedback("");

    try {
      const stored = localStorage.getItem("pdmk-auth");
      const parsed = stored ? JSON.parse(stored) : null;
      const apiBase = parsed?.state?.baseUrl || "http://localhost:8000";
      const apiKey = parsed?.state?.apiKey || "";
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
      };

      setSubmitting(true);
      const res = await fetch(`${apiBase}/api/v1/runs/${slug}/resume`, {
        method: "POST",
        headers,
        body: JSON.stringify({ answers: { answer } }),
      });

      if (res.ok) {
        toast({ title: "✅ Response sent", description: `Answer: ${answer}` });
        setResolved(true);
        setAnswers({ 0: answer });
        onResolved?.();
        onClose();
      } else {
        const err = await res.json().catch(() => ({}));
        toast({ title: "❌ Failed", description: err.detail || "Error", variant: "destructive" });
      }
    } catch (e: any) {
      toast({ title: "❌ Error", description: e.message, variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  if (resolved) {
    return null;
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v && !submitting) onClose(); }}>
      <DialogContent className="sm:max-w-md" data-testid="hitl-dialog">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <DialogTitle className="text-sm font-medium">✋ Human-in-the-Loop</DialogTitle>
            <Badge variant="outline" className="text-xs text-amber-400 border-amber-500/30 font-mono">
              {state}
            </Badge>
          </div>
          <DialogDescription className="text-xs text-muted-foreground">
            Run <span className="font-mono text-primary">{slug}</span> is waiting for your input
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Timeout warning */}
          {countdown > 0 && countdown < 300 && (
            <div className={cn(
              "flex items-center gap-2 px-3 py-2 rounded-md text-xs border",
              countdown < 60
                ? "bg-red-500/10 border-red-500/20 text-red-400"
                : "bg-amber-500/10 border-amber-500/20 text-amber-400"
            )}>
              <Clock className="w-3.5 h-3.5 shrink-0" />
              <span>
                {countdown < 60
                  ? `Timeout in ${countdown}s — response required!`
                  : `Auto-resume in ${Math.floor(countdown / 60)}m`}
              </span>
              <Badge variant="outline" className="text-[10px] ml-auto font-mono">
                {Math.floor(countdown / 60)}:{(countdown % 60).toString().padStart(2, "0")}
              </Badge>
            </div>
          )}

          {/* Current question */}
          {question && (
            <div className="space-y-2">
              <p className="text-sm font-medium">
                Question {currentQ + 1}/{questions.length}
              </p>
              <p className="text-sm text-foreground">{question.question}</p>

              {/* Yes/No */}
              {question.type === "yes_no" && (
                <div className="flex gap-2 pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    className={cn(
                      "flex-1",
                      answers[currentQ] === "yes" || answers[currentQ] === "evet"
                        ? "border-emerald-500/50 text-emerald-400 bg-emerald-500/10"
                        : ""
                    )}
                    onClick={() => handleAnswer("evet")}
                    disabled={submitting}
                  >
                    ✅ Yes / Evet
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className={cn(
                      "flex-1",
                      answers[currentQ] === "no" || answers[currentQ] === "hayır"
                        ? "border-red-500/50 text-red-400 bg-red-500/10"
                        : ""
                    )}
                    onClick={() => handleAnswer("hayır")}
                    disabled={submitting}
                  >
                    ❌ No / Hayır
                  </Button>
                  {/* Quick resume buttons */}
                  <div className="flex gap-1 ml-auto">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 text-xs text-emerald-400"
                      onClick={() => handleQuickResume("evet")}
                      disabled={submitting}
                    >
                      {submitting ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3 mr-1" />}
                      Yes
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 text-xs text-red-400"
                      onClick={() => handleQuickResume("hayır")}
                      disabled={submitting}
                    >
                      No
                    </Button>
                  </div>
                </div>
              )}

              {/* Multiple Choice */}
              {question.type === "multiple_choice" && question.choices && (
                <div className="grid grid-cols-2 gap-2 pt-1">
                  {question.choices.map((choice) => (
                    <Button
                      key={choice}
                      variant="outline"
                      size="sm"
                      className={cn(
                        "text-xs h-auto py-2",
                        answers[currentQ] === choice
                          ? "border-primary text-primary bg-primary/10"
                          : ""
                      )}
                      onClick={() => {
                        handleAnswer(choice);
                        // Auto-submit for multiple choice (single selection)
                        handleQuickResume(choice);
                      }}
                      disabled={submitting}
                    >
                      {choice}
                    </Button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Feedback textarea */}
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">Feedback (optional)</label>
            <Textarea
              placeholder="Add your feedback or reason..."
              className="text-sm min-h-16 resize-none"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              disabled={submitting}
            />
          </div>

          {/* Action buttons */}
          <div className="flex gap-2 pt-1">
            <Button variant="outline" size="sm" onClick={onClose} disabled={submitting} className="flex-1">
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={!answers[currentQ] || submitting}
              className="flex-1"
              data-testid="button-hitl-submit"
            >
              {submitting ? (
                <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
              ) : (
                <Send className="w-4 h-4 mr-1.5" />
              )}
              {isLast ? "Submit & Resume" : "Next Question"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
