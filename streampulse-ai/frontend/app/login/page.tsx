"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Lock, Zap } from "lucide-react";
import { post } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { ErrorNote } from "@/components/ui/misc";

export default function LoginPage() {
  const auth = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const setup = auth.data?.setup_required;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (setup && password !== confirm) return setError("Passwords do not match");
    setBusy(true);
    try {
      await post(setup ? "/api/auth/setup" : "/api/auth/login", { username, password });
      await qc.invalidateQueries({ queryKey: ["auth"] });
      router.replace("/dashboard");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(ellipse_at_top,hsl(262_83%_64%/0.15),transparent_60%)] p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <span className="mb-2 flex h-11 w-11 items-center justify-center rounded-xl bg-primary"><Zap className="h-5 w-5 text-white" /></span>
          <CardTitle className="text-lg">StreamPulse AI</CardTitle>
          <CardDescription>{setup ? "Create the owner account for this private installation." : "Sign in to your private clipping studio."}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="u">Username</Label>
              <Input id="u" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required minLength={3} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p">Password</Label>
              <Input id="p" type="password" autoComplete={setup ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} required />
              {setup && <p className="text-[11px] text-muted-foreground">At least 12 characters, mixing 3 of: lowercase, uppercase, digits, symbols.</p>}
            </div>
            {setup && (
              <div className="space-y-1.5">
                <Label htmlFor="c">Confirm password</Label>
                <Input id="c" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
              </div>
            )}
            <ErrorNote error={error} />
            <Button className="w-full" disabled={busy || auth.isLoading}>
              <Lock /> {setup ? "Create owner account" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
