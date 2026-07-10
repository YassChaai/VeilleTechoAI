"use client";

import { useState } from "react";
import { Bookmark, Star } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { Input } from "./ui/input";
import { Label } from "./ui/label";

const NO_FOLDER = "none";

export function SaveDialog({
  articleId,
  folders,
  initialSaved,
  initialFolderId,
  initialFolderName,
}: {
  articleId: number;
  folders: { id: number; name: string }[];
  initialSaved: boolean;
  initialFolderId: number | null;
  initialFolderName: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(initialSaved);
  const [folderName, setFolderName] = useState(initialFolderName);
  const [folderId, setFolderId] = useState<string>(
    initialFolderId ? String(initialFolderId) : NO_FOLDER
  );
  const [newFolder, setNewFolder] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      const opts: { folder_id?: number; new_folder?: string } = {};
      if (newFolder.trim()) opts.new_folder = newFolder.trim();
      else if (folderId !== NO_FOLDER) opts.folder_id = Number(folderId);
      await api.save(articleId, opts);
      setSaved(true);
      setFolderName(newFolder.trim() || folders.find((f) => String(f.id) === folderId)?.name || null);
      setNewFolder("");
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await api.unsave(articleId);
      setSaved(false);
      setFolderName(null);
      setFolderId(NO_FOLDER);
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={saved ? "secondary" : "default"}>
          {saved ? (
            <>
              <Star className="fill-current" /> Enregistré{folderName ? ` · ${folderName}` : ""}
            </>
          ) : (
            <>
              <Bookmark /> Lire plus tard
            </>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Enregistrer l&apos;article</DialogTitle>
          <DialogDescription>
            Classe-le dans un dossier thématique, ou laisse-le dans « À lire ».
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-1">
          <div className="grid gap-2">
            <Label>Dossier existant</Label>
            <Select value={folderId} onValueChange={setFolderId} disabled={!!newFolder.trim()}>
              <SelectTrigger>
                <SelectValue placeholder="À lire (sans dossier)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_FOLDER}>À lire (sans dossier)</SelectItem>
                {folders.map((f) => (
                  <SelectItem key={f.id} value={String(f.id)}>
                    {f.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="new-folder">…ou nouveau dossier</Label>
            <Input
              id="new-folder"
              placeholder="ex. IA générative"
              value={newFolder}
              onChange={(e) => setNewFolder(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          {saved && (
            <Button variant="destructive" onClick={remove} disabled={busy} className="sm:mr-auto">
              Retirer
            </Button>
          )}
          <Button onClick={submit} disabled={busy}>
            {saved ? "Mettre à jour" : "Enregistrer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
