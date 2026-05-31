type CollectionEntryLike = {
  id: string;
  slug?: string;
};

export function getCollectionFileSlug(entry: CollectionEntryLike): string {
  return entry.slug ?? entry.id.replace(/\.[^/.]+$/, '');
}

export function getCollectionRouteSlug(entry: CollectionEntryLike): string {
  return getCollectionFileSlug(entry).replace(/^collection-/, '');
}
