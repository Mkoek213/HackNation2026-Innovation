"use client";

import { Dialog as Primitive } from "@base-ui/react/dialog";
import { X } from "./icons";
import { Button } from "./button";

export function Dialog({ open, onClose, title, children, className = "" }: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode; className?: string;
}) {
  return <Primitive.Root open={open} onOpenChange={(value) => { if (!value) onClose(); }}>
    <Primitive.Portal><Primitive.Backdrop className="modal-backdrop" />
      <Primitive.Popup className={`modal ${className}`}>
        <Primitive.Close render={<Button variant="ghost" size="icon" className="modal-close" aria-label="Zamknij" />}><X aria-hidden="true" /></Primitive.Close>
        <Primitive.Title className="modal-title">{title}</Primitive.Title>
        {children}
      </Primitive.Popup>
    </Primitive.Portal>
  </Primitive.Root>;
}
