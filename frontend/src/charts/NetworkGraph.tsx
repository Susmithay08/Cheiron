/**
 * Force-directed network with pan, zoom, hover and click-to-cite.
 *
 * d3-force computes the layout; rendering is plain SVG so nodes stay
 * selectable and the whole thing remains dependency-light.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";

import type { Datum, GraphEdge, GraphNode, Visualization } from "../types/api";
import { groupColor } from "./palette";

type SimNode = SimulationNodeDatum & GraphNode;
type SimLink = SimulationLinkDatum<SimNode> & { weight: number; raw: GraphEdge };

const WIDTH = 900;
const HEIGHT = 520;

interface Props {
  visualization: Visualization;
  onSelect: (datum: Datum) => void;
}

export function NetworkGraph({ visualization, onSelect }: Props) {
  const nodes = visualization.nodes ?? [];
  const edges = visualization.edges ?? [];

  const [tick, setTick] = useState(0);
  const [hovered, setHovered] = useState<string | null>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const dragRef = useRef<{ x: number; y: number } | null>(null);

  const { simNodes, simLinks } = useMemo(() => {
    const simNodes: SimNode[] = nodes.map((n) => ({ ...n }));
    const byId = new Map(simNodes.map((n) => [n.id, n]));
    const simLinks: SimLink[] = edges
      .filter((e) => byId.has(e.source) && byId.has(e.target))
      .map((e) => ({
        source: byId.get(e.source)!,
        target: byId.get(e.target)!,
        weight: e.weight,
        raw: e,
      }));
    return { simNodes, simLinks };
  }, [nodes, edges]);

  useEffect(() => {
    const simulation = forceSimulation(simNodes)
      .force("charge", forceManyBody().strength(-420))
      .force("link", forceLink<SimNode, SimLink>(simLinks).id((d) => d.id).distance(110).strength(0.35))
      .force("center", forceCenter(WIDTH / 2, HEIGHT / 2))
      .force("collide", forceCollide<SimNode>().radius((d) => 14 + Math.min(d.trial_count, 40) / 4))
      .on("tick", () => setTick((t) => t + 1));

    return () => void simulation.stop();
  }, [simNodes, simLinks]);

  const maxWeight = Math.max(1, ...simLinks.map((l) => l.weight));
  const groups = [...new Set(nodes.map((n) => n.group))];

  const isDimmed = (id: string) =>
    hovered !== null &&
    hovered !== id &&
    !simLinks.some(
      (l) =>
        ((l.source as SimNode).id === hovered && (l.target as SimNode).id === id) ||
        ((l.target as SimNode).id === hovered && (l.source as SimNode).id === id),
    );

  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl bg-slate-50">
      <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-3 rounded-lg bg-white/90 px-3 py-2 text-xs shadow-sm">
        {groups.map((group, index) => (
          <span key={group} className="flex items-center gap-1.5 capitalize text-slate-600">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: groupColor(group, index) }}
            />
            {group}
          </span>
        ))}
        <span className="text-slate-400">drag to pan · scroll to zoom · click an edge to cite it</span>
      </div>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-full w-full cursor-grab active:cursor-grabbing"
        data-tick={tick}
        onMouseDown={(e) => (dragRef.current = { x: e.clientX, y: e.clientY })}
        onMouseUp={() => (dragRef.current = null)}
        onMouseLeave={() => (dragRef.current = null)}
        onMouseMove={(e) => {
          if (!dragRef.current) return;
          const dx = e.clientX - dragRef.current.x;
          const dy = e.clientY - dragRef.current.y;
          dragRef.current = { x: e.clientX, y: e.clientY };
          setTransform((t) => ({ ...t, x: t.x + dx, y: t.y + dy }));
        }}
        onWheel={(e) => {
          const next = Math.min(3, Math.max(0.4, transform.k * (e.deltaY < 0 ? 1.12 : 0.89)));
          setTransform((t) => ({ ...t, k: next }));
        }}
      >
        <g transform={`translate(${transform.x},${transform.y}) scale(${transform.k})`}>
          {simLinks.map((link, index) => {
            const source = link.source as SimNode;
            const target = link.target as SimNode;
            const dim = isDimmed(source.id) && isDimmed(target.id);
            return (
              <line
                key={index}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke="#94a3b8"
                strokeOpacity={dim ? 0.12 : 0.45}
                strokeWidth={1 + (link.weight / maxWeight) * 5}
                className="cursor-pointer"
                onClick={() => onSelect(link.raw)}
              >
                <title>
                  {source.label} ↔ {target.label}: {link.weight} shared studies
                </title>
              </line>
            );
          })}

          {simNodes.map((node, index) => {
            const radius = 6 + Math.min(node.trial_count, 60) / 6;
            const dim = isDimmed(node.id);
            return (
              <g
                key={node.id}
                transform={`translate(${node.x ?? 0},${node.y ?? 0})`}
                opacity={dim ? 0.2 : 1}
                onMouseEnter={() => setHovered(node.id)}
                onMouseLeave={() => setHovered(null)}
                className="cursor-pointer"
              >
                <circle r={radius} fill={groupColor(node.group, index)} fillOpacity={0.85} stroke="#fff" strokeWidth={1.5} />
                <text
                  x={radius + 4}
                  y={4}
                  fontSize={11}
                  fill="#334155"
                  className="pointer-events-none select-none"
                >
                  {node.label.length > 26 ? `${node.label.slice(0, 26)}…` : node.label}
                </text>
                <title>
                  {node.label} · {node.group} · {node.trial_count} studies · {node.degree} connections
                </title>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
