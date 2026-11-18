import { Instagram, Music2, Youtube } from "lucide-react";

export const PLATFORMS = [
  { key: "youtube", label: "YouTube Shorts", icon: Youtube, color: "text-red-500" },
  { key: "tiktok", label: "TikTok", icon: Music2, color: "text-cyan-400" },
  { key: "instagram", label: "Instagram Reels", icon: Instagram, color: "text-pink-500" },
] as const;
