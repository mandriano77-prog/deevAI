"use client";

import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import type { ActionRead } from "@/lib/api/actions";
import { microcopy, sectionCls } from "./shared";

function SortableStep({ action }: { action: ActionRead }) {
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id: action.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <li
      ref={setNodeRef}
      style={style}
      className="flex cursor-grab items-center gap-3 rounded-md border border-ink-700 bg-ink-800/80 px-3 py-2 active:cursor-grabbing"
      {...attributes}
      {...listeners}
    >
      <span className="text-ink-500" aria-hidden>
        ⋮⋮
      </span>
      <span className="text-sm text-ink-100">
        {action.funnel_position}. {action.name}
      </span>
      <span className="ml-auto text-xs text-ink-400">
        {action.weight} pt · {action.value_eur} €
      </span>
    </li>
  );
}

interface Props {
  funnel: ActionRead[];
  onReorder: (orderedIds: string[]) => Promise<void>;
}

export function ActionFunnelBuilder({ funnel, onReorder }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  async function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = funnel.findIndex((a) => a.id === active.id);
    const newIndex = funnel.findIndex((a) => a.id === over.id);
    const next = arrayMove(funnel, oldIndex, newIndex);
    await onReorder(next.map((a) => a.id));
  }

  return (
    <section aria-labelledby="funnel-heading">
      <h2 id="funnel-heading" className="mb-2 text-sm font-medium text-ink-50">
        Funnel action
      </h2>
      <div className={sectionCls}>
        {funnel.length === 0 ? (
          <p className="py-4 text-sm text-ink-500">
            Aggiungi action al catalogo e trascinale qui per definire il funnel.
          </p>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={(e) => void handleDragEnd(e)}
          >
            <SortableContext
              items={funnel.map((a) => a.id)}
              strategy={verticalListSortingStrategy}
            >
              <ul className="space-y-2 py-2" role="list">
                {funnel.map((a) => (
                  <SortableStep key={a.id} action={a} />
                ))}
              </ul>
            </SortableContext>
          </DndContext>
        )}
      </div>
      <p className="mt-2 text-xs text-ink-500">{microcopy}</p>
    </section>
  );
}
