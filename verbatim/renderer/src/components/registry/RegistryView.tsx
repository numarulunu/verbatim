import { useEffect, useRef, useState } from 'react';
import { UserPlus } from 'lucide-react';
import { PersonsTable } from './PersonsTable';
import { PersonDetail } from './PersonDetail';
import { CollisionsPanel } from './CollisionsPanel';
import { Modal } from '../ui/Modal';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { Select } from '../ui/Select';
import { Collision, Person } from '../../types';
import { verbatimClient } from '../../bridge/verbatimClient';

export function RegistryView({
  pushToast,
}: {
  pushToast: (t: { kind: 'error' | 'warning' | 'info'; title: string; body?: string }) => void;
}) {
  const [persons, setPersons] = useState<Person[]>([]);
  const [collisions, setCollisions] = useState<Collision[]>([]);
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const [inspectedPerson, setInspectedPerson] = useState<Person | undefined>();
  const [modal, setModal] = useState<'edit' | 'rename' | 'merge' | null>(null);
  const [renameVal, setRenameVal] = useState('');
  const [mergeTarget, setMergeTarget] = useState('');
  const [editDisplayName, setEditDisplayName] = useState('');
  const [editRole, setEditRole] = useState<Person['role']>('unknown');
  const [editVoiceType, setEditVoiceType] = useState('');
  const [editFach, setEditFach] = useState('');
  const selectedIdRef = useRef<string | undefined>();

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    let alive = true;

    verbatimClient.listPersons().catch((error) => {
      if (!alive) {
        return;
      }
      pushToast({
        kind: 'error',
        title: 'Registry load failed',
        body: error instanceof Error ? error.message : 'Could not load persons.',
      });
    });

    const off = verbatimClient.onEvent((event) => {
      if (event.type === 'persons_listed') {
        setPersons(event.persons);
        setSelectedId((current) => {
          if (current && event.persons.some((person) => person.id === current)) {
            return current;
          }
          return event.persons[0]?.id;
        });
        setInspectedPerson((current) => {
          if (current && event.persons.some((person) => person.id === current.id)) {
            return current;
          }
          return undefined;
        });
        return;
      }

      if (event.type === 'person_inspected') {
        if (event.person.id === selectedIdRef.current) {
          setInspectedPerson(event.person);
        }
        setPersons((current) => current.map((person) => (person.id === event.person.id ? { ...person, ...event.person } : person)));
        return;
      }

      if (event.type === 'person_renamed') {
        setPersons((current) => current.map((person) => (person.id === event.old_id ? { ...person, id: event.new_id } : person)));
        setInspectedPerson((current) => (current?.id === event.old_id ? { ...current, id: event.new_id } : current));
        setSelectedId((current) => (current === event.old_id ? event.new_id : current));
        return;
      }

      if (event.type === 'person_merged') {
        setPersons((current) => current.filter((person) => person.id !== event.source_id));
        setCollisions((current) => current.filter((collision) => collision.a !== event.source_id && collision.b !== event.source_id));
        setInspectedPerson((current) => (current?.id === event.source_id ? undefined : current));
        setSelectedId((current) => (current === event.source_id ? event.target_id : current));
        return;
      }

      if (event.type === 'collision_detected') {
        const next = { a: event.pair[0], b: event.pair[1], similarity: event.cosine };
        setCollisions((current) => {
          const key = [next.a, next.b].sort().join('|');
          const filtered = current.filter((collision) => [collision.a, collision.b].sort().join('|') !== key);
          return [...filtered, next];
        });
      }
    });

    return () => {
      alive = false;
      off();
    };
  }, [pushToast]);

  useEffect(() => {
    if (!selectedId) {
      return;
    }

    verbatimClient.inspectPerson(selectedId).catch((error) => {
      pushToast({
        kind: 'error',
        title: 'Person inspect failed',
        body: error instanceof Error ? error.message : 'Could not load person details.',
      });
    });
  }, [pushToast, selectedId]);

  const selected = inspectedPerson?.id === selectedId
    ? inspectedPerson
    : persons.find((person) => person.id === selectedId);

  const openRename = () => {
    if (!selected) return;
    setRenameVal(selected.id);
    setModal('rename');
  };

  const openMerge = () => {
    if (!selected) return;
    const first = persons.find((person) => person.id !== selected.id);
    setMergeTarget(first?.id || '');
    setModal('merge');
  };

  const openEdit = () => {
    if (!selected) return;
    setEditDisplayName(selected.displayName);
    setEditRole(selected.role);
    setEditVoiceType(selected.voiceType || '');
    setEditFach(selected.fach || '');
    setModal('edit');
  };

  const doEdit = async () => {
    if (!selected) return;

    const updates: Record<string, unknown> = {};
    const displayName = editDisplayName.trim();
    const voiceType = editVoiceType.trim();
    const fach = editFach.trim();

    if (displayName) {
      updates.display_name = displayName;
    }
    if (editRole === 'teacher' || editRole === 'student') {
      updates.default_role = editRole;
    }
    if (voiceType) {
      updates.voice_type = voiceType;
    }
    if (fach) {
      updates.fach = fach;
    }

    try {
      await verbatimClient.editPerson(selected.id, updates);
      await verbatimClient.inspectPerson(selected.id);
      await verbatimClient.listPersons();
      pushToast({ kind: 'info', title: 'Person updated', body: selected.id });
      setModal(null);
    } catch (error) {
      pushToast({
        kind: 'error',
        title: 'Edit failed',
        body: error instanceof Error ? error.message : 'Could not save person changes.',
      });
    }
  };

  const doRename = async () => {
    if (!selected || !renameVal.trim()) return;

    const nextId = renameVal.trim();
    if (nextId === selected.id) {
      setModal(null);
      return;
    }

    try {
      await verbatimClient.renamePerson(selected.id, nextId);
      setSelectedId(nextId);
      setInspectedPerson(undefined);
      await verbatimClient.listPersons();
      pushToast({ kind: 'info', title: 'Person renamed', body: `${selected.id} -> ${nextId}` });
      setModal(null);
    } catch (error) {
      pushToast({
        kind: 'error',
        title: 'Rename failed',
        body: error instanceof Error ? error.message : 'Could not rename the person.',
      });
    }
  };

  const doMerge = async () => {
    if (!selected || !mergeTarget || mergeTarget === selected.id) return;

    try {
      await verbatimClient.mergePersons(selected.id, mergeTarget);
      setSelectedId(mergeTarget);
      setInspectedPerson(undefined);
      await verbatimClient.listPersons();
      pushToast({ kind: 'info', title: 'Persons merged', body: `${selected.id} -> ${mergeTarget}` });
      setModal(null);
    } catch (error) {
      pushToast({
        kind: 'error',
        title: 'Merge failed',
        body: error instanceof Error ? error.message : 'Could not merge the people.',
      });
    }
  };

  if (persons.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center max-w-md">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-accent-soft flex items-center justify-center">
            <UserPlus size={20} className="text-accent" />
          </div>
          <h3 className="text-md font-semibold text-ink-50 mb-1">No one registered yet</h3>
          <p className="text-sm text-ink-400">Run a batch to auto-discover voices.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full p-4 gap-3 min-h-0">
      <div className="grid grid-cols-[1.2fr_1fr] gap-3 flex-1 min-h-0">
        <div className="flex flex-col gap-3 min-h-0">
          <PersonsTable persons={persons} selectedId={selectedId} onSelect={setSelectedId} />
          <CollisionsPanel collisions={collisions} persons={persons} />
        </div>
        <PersonDetail person={selected} onEdit={openEdit} onRename={openRename} onMerge={openMerge} />
      </div>

      <Modal
        open={modal === 'rename'}
        onClose={() => setModal(null)}
        title="Rename person"
        description={selected?.id}
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)}>Cancel</Button>
            <Button variant="primary" onClick={doRename}>Save</Button>
          </>
        }
      >
        <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">New person ID</label>
        <Input value={renameVal} onChange={(e) => setRenameVal(e.target.value)} autoFocus mono />
      </Modal>

      <Modal
        open={modal === 'merge'}
        onClose={() => setModal(null)}
        title="Merge person"
        description="All sessions and voiceprints move to the target. This cannot be undone."
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)}>Cancel</Button>
            <Button variant="danger" onClick={doMerge}>Merge</Button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">Source</label>
            <div className="h-8 rounded bg-ink-850 border border-ink-700/60 px-2.5 flex items-center text-sm text-ink-200">
              {selected?.displayName} <span className="ml-2 font-mono text-2xs text-ink-500">{selected?.id}</span>
            </div>
          </div>
          <div>
            <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">Merge into</label>
            <Select
              value={mergeTarget}
              onChange={setMergeTarget}
              options={persons
                .filter((person) => person.id !== selected?.id)
                .map((person) => ({ value: person.id, label: `${person.displayName} - ${person.id}` }))}
            />
          </div>
        </div>
      </Modal>

      <Modal
        open={modal === 'edit'}
        onClose={() => setModal(null)}
        title="Edit person"
        description={selected?.id}
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(null)}>Cancel</Button>
            <Button variant="primary" onClick={doEdit}>Save</Button>
          </>
        }
      >
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">Display name</label>
            <Input value={editDisplayName} onChange={(e) => setEditDisplayName(e.target.value)} />
          </div>
          <div>
            <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">Role</label>
            <Select
              value={editRole}
              onChange={(value) => setEditRole(value as Person['role'])}
              options={[
                { value: 'teacher', label: 'teacher' },
                { value: 'student', label: 'student' },
                { value: 'unknown', label: 'unknown' },
              ]}
            />
          </div>
          <div>
            <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">Voice type</label>
            <Input value={editVoiceType} onChange={(e) => setEditVoiceType(e.target.value)} />
          </div>
          <div>
            <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">Fach</label>
            <Input value={editFach} onChange={(e) => setEditFach(e.target.value)} />
          </div>
        </div>
      </Modal>
    </div>
  );
}
