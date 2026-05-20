import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useCreateRun, useListProfiles, getListRunsQueryKey } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/hooks/use-toast";
import { MOCK_PROFILES } from "@/lib/mock-data";

const schema = z.object({
  profile: z.string().min(1, "Profile is required"),
  title: z.string().min(1, "Title is required"),
});

type FormData = z.infer<typeof schema>;

export default function CreateRunDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: profiles } = useListProfiles();
  const displayProfiles = profiles ?? MOCK_PROFILES;
  const createRun = useCreateRun();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const { register, handleSubmit, formState: { errors }, setValue, reset } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { profile: "", title: "" },
  });

  const onSubmit = (data: FormData) => {
    createRun.mutate(
      { data: { profile: data.profile, title: data.title } },
      {
        onSuccess: (run) => {
          toast({ title: "Run created", description: `${run.slug} is now active.` });
          queryClient.invalidateQueries({ queryKey: getListRunsQueryKey() });
          reset();
          onClose();
        },
        onError: () => {
          toast({ title: "Failed to create run", variant: "destructive" });
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create New Run</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <Label>Profile</Label>
            <Select onValueChange={(v) => setValue("profile", v)}>
              <SelectTrigger data-testid="select-profile">
                <SelectValue placeholder="Select a profile" />
              </SelectTrigger>
              <SelectContent>
                {displayProfiles.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.profile && <p className="text-xs text-destructive">{errors.profile.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label>Title</Label>
            <Input placeholder="Enter run title..." data-testid="input-run-title" {...register("title")} />
            {errors.title && <p className="text-xs text-destructive">{errors.title.message}</p>}
          </div>
          <div className="flex gap-2 justify-end pt-2">
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={createRun.isPending} data-testid="button-create-run">
              {createRun.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Create Run
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
