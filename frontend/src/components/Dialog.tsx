import { useEffect, useRef } from "react";
import { X } from "@phosphor-icons/react";

export function Dialog({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const element = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    element.current?.showModal();
  }, []);
  return (
    <dialog
      className="workspace-dialog glass"
      ref={element}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === element.current) onClose();
      }}
    >
      <div className="dialog-heading">
        <h2>{title}</h2>
        <button
          aria-label="Close panel"
          className="icon-button"
          onClick={onClose}
        >
          <X size={23} />
        </button>
      </div>
      <div className="dialog-body">{children}</div>
    </dialog>
  );
}
