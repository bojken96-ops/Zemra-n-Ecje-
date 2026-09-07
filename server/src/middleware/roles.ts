import { NextFunction, Response } from "express";
import { AuthedRequest } from "./auth";

export function requireRole(...roles: string[]) {
  return (req: AuthedRequest, res: Response, next: NextFunction) => {
    if (!req.user || !roles.includes(req.user.role)) {
      return res.status(403).json({ error: "Permessi insufficienti" });
    }
    next();
  };
}

export const canWrite = requireRole("ADMIN", "TESORIERE");
export const adminOnly = requireRole("ADMIN");
