import { Copy, ExternalLink, Star, Users } from 'lucide-react'

export default function ListingDetails({ listing, favorites, toggleFavorite, setSellerFilter, onViewSeller }) {
  const favorite = listing && favorites.some((item) => item.listing_link === listing.listing_link)
  if (!listing) {
    return (
      <aside className="hidden w-80 shrink-0 border-l border-line bg-[#080E1D] p-5 xl:block">
        <h3 className="text-lg font-bold">Listing Details</h3>
        <p className="mt-3 text-sm text-slate-400">Select a listing to see details.</p>
      </aside>
    )
  }
  return (
    <aside className="hidden w-80 shrink-0 overflow-y-auto border-l border-line bg-[#080E1D] p-5 xl:block">
      <h3 className="text-lg font-bold">Listing Details</h3>
      <div className="mt-5 rounded-3xl bg-panel p-5">
        <div className="text-4xl font-black">{listing.plate_number}</div>
        <div className="mt-2 text-slate-400">{listing.city} • Code {listing.code}</div>
        <div className="mt-4 text-2xl font-bold text-emerald-300">{listing.price}</div>
      </div>
      <div className="mt-5 space-y-3 text-sm">
        {[
          ['Seller', listing.seller_name],
          ['Username', listing.seller_username],
          ['Phone', listing.phone_number],
          ['Uploaded', `${listing.uploaded_date} ${listing.uploaded_time}`],
          ['Age', listing.age_text],
          ['Deal Rank', listing.deal_rank],
          ['Favorite', favorite ? 'Yes' : 'No']
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-line bg-panel/70 p-3">
            <p className="text-xs uppercase text-slate-500">{label}</p>
            <p className="mt-1 break-words font-medium">{value || '?'}</p>
          </div>
        ))}
      </div>
      <div className="mt-5 grid gap-3">
        <button className="btn-primary flex items-center justify-center gap-2" onClick={() => window.open(listing.listing_link, '_blank')}><ExternalLink size={16} />Open listing</button>
        <button className="btn-muted flex items-center justify-center gap-2" onClick={() => window.open(listing.seller_link, '_blank')}><Users size={16} />Open seller profile</button>
        <button className="btn-muted flex items-center justify-center gap-2" onClick={() => navigator.clipboard.writeText(listing.phone_number || '')}><Copy size={16} />Copy phone</button>
        {onViewSeller && <button className="btn-secondary flex items-center justify-center gap-2" onClick={() => onViewSeller(listing)}><Users size={16} />View seller plates</button>}
        <button className="btn-muted flex items-center justify-center gap-2" onClick={() => toggleFavorite(listing)}><Star size={16} />{favorite ? 'Remove favorite' : 'Add favorite'}</button>
      </div>
    </aside>
  )
}
