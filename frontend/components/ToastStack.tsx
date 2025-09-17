'use client';

import { XMarkIcon } from '@heroicons/react/24/outline';
import type { ReactNode } from 'react';

export type ToastVariant = 'info' | 'success' | 'error';

export interface ToastDescriptor {
  id: string;
  message: ReactNode;
  variant?: ToastVariant;
}

interface ToastStackProps {
  toasts: ToastDescriptor[];
  onDismiss: (id: string) => void;
}

const variantStyles: Record<ToastVariant, string> = {
  info: 'bg-slate-900/90 text-slate-50',
  success: 'bg-emerald-600 text-white',
  error: 'bg-rose-600 text-white',
};

export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
  if (!toasts.length) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed top-6 right-6 z-50 flex max-w-sm flex-col gap-3">
      {toasts.map((toast) => {
        const variant = toast.variant ?? 'info';
        return (
          <div
            key={toast.id}
            className={`pointer-events-auto flex items-start gap-3 rounded-xl px-4 py-3 text-sm shadow-lg ring-1 ring-black/10 transition hover:shadow-xl ${variantStyles[variant]}`}
          >
            <span className="flex-1 leading-tight">{toast.message}</span>
            <button
              type="button"
              onClick={() => onDismiss(toast.id)}
              className="inline-flex shrink-0 rounded-full p-1 text-slate-100/80 transition hover:bg-white/10 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/60"
              aria-label="Dismiss notification"
            >
              <XMarkIcon className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
