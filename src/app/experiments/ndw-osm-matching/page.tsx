import type { Metadata } from "next";
import MatchingCompare from "@/components/ndw-osm/MatchingCompare";

export const metadata: Metadata = {
  title: "NDW-OSM matching",
  description: "NDW sites matched onto OSM roads",
};

export default function NdwOsmMatchingPage() {
  return <MatchingCompare />;
}
