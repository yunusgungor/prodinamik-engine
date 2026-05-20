import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useTransitionRun, getGetRunQueryKey, getListRunsQueryKey } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/hooks/use-toast";

export default function TransitionDialog({
  slug,
  transitions,
  onClose,
}: {
  slug: string;
  transitions: string[];
  onClose: () => void;
}) {
  const [selected, setSelected] = useState("");
  const [reason, setReason] = useState("");
  const transitionRun = useTransitionRun();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const onSubmit = () => {
    if (!selected) return;
    transitionRun.mutate(
      { slug, data: { transition: selected, reason } },
      {
        onSuccess: () => {
          toast({ title: "Transition applied", description: `Run ${slug}: ${selected}` });
          queryClient.invalidateQueries({ queryKey: getGetRunQueryKey(slug) });
          queryClient.invalidateQueries({ queryKey: getListRunsQueryKey() });
          onClose();
        },
        onError: () => {
          toast({ title: "Transition failed", variant: "destructive" });
        },
      }
    );
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Transition Run</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground font-mono">{slug}</p>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Transition</Label>
            <Select value={selected} onValueChange={setSelected}>
              <SelectTrigger data-testid="select-transition">
                <SelectValue placeholder="Select transition..." />
              </SelectTrigger>
              <SelectContent>
                {transitions.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Reason (optional)</Label>
            <Textarea
              placeholder="Reason for transition..."
              className="text-sm min-h-16"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              data-testid="textarea-reason"
            />
          </div>
          <div className="flex gap-2 justify-end">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button disabled={!selected || transitionRun.isPending} onClick={onSubmit} data-testid="button-confirm-transition">
              {transitionRun.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Apply Transition
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
