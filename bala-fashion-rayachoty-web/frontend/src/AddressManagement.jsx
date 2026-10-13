import { useCallback, useEffect, useState } from 'react'
import { Check, MapPin, Pencil, Plus, RefreshCw, Trash2, X } from 'lucide-react'
import { api } from './api'

const emptyAddress = { recipient_name:'', phone:'', line1:'', line2:'', landmark:'', city:'Rayachoty', state:'Andhra Pradesh', postal_code:'', latitude:'', longitude:'', notes:'', is_default:false }

export function AddressManagement({ session, notify, onChoose, returnTo = 'account' }) {
  const [addresses, setAddresses] = useState([])
  const [form, setForm] = useState(emptyAddress)
  const [editingId, setEditingId] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!session?.access_token) return
    setLoading(true)
    try {
      const data = await api('/addresses/', { token: session.access_token })
      setAddresses(data.results || [])
      setError('')
    } catch (err) {
      setError(err.message || 'Saved addresses could not be loaded.')
    } finally { setLoading(false) }
  }, [session?.access_token])

  useEffect(() => { load() }, [load])

  function edit(address) {
    setEditingId(address.id)
    setForm({ ...emptyAddress, ...address, latitude:String(address.latitude ?? ''), longitude:String(address.longitude ?? '') })
    document.querySelector('.address-editor')?.scrollIntoView({ behavior:'smooth', block:'start' })
  }

  function reset() { setEditingId(''); setForm(emptyAddress) }

  async function save(event) {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    try {
      const payload = { ...form, latitude:Number(form.latitude), longitude:Number(form.longitude) }
      await api('/addresses/', { method:editingId ? 'PATCH' : 'POST', token:session.access_token, body:JSON.stringify({ ...payload, ...(editingId ? { id:editingId } : {}) }) })
      await load()
      reset()
      notify(editingId ? 'Address updated.' : 'Address saved.')
    } catch (err) {
      notify(err.message || 'Address could not be saved.')
    } finally { setSaving(false) }
  }

  async function makeDefault(address) {
    setSaving(true)
    try {
      await api('/addresses/', { method:'PATCH', token:session.access_token, body:JSON.stringify({ ...address, is_default:true }) })
      await load()
      notify('Default delivery address updated.')
    } catch (err) { notify(err.message || 'Could not set default address.') }
    finally { setSaving(false) }
  }

  async function remove(address) {
    if (!window.confirm('Delete this saved delivery address?')) return
    setSaving(true)
    try {
      await api('/addresses/?id=' + encodeURIComponent(address.id), { method:'DELETE', token:session.access_token })
      await load()
      if (editingId === address.id) reset()
      notify('Address deleted.')
    } catch (err) { notify(err.message || 'Address could not be deleted.') }
    finally { setSaving(false) }
  }

  return <div className="drawer-body seller-dashboard address-management">
    <div className="seller-dashboard-head">
      <div><b>Saved delivery addresses</b><small>Create, edit or remove addresses. One address can be your default.</small></div>
      <button type="button" className="secondary" onClick={load} disabled={loading}><RefreshCw size={14}/> Refresh</button>
    </div>
    {error && <div className="warning">{error}</div>}
    {loading ? <p>Loading saved addresses…</p> : !addresses.length ? <p className="seller-empty">No saved addresses yet. Add one below.</p> : addresses.map(address =>
      <article className="seller-store-row saved-address-row" key={address.id}>
        <span><b>{address.recipient_name} {address.is_default && <small className="seller-status approved">Default</small>}</b><small>{address.phone}</small><small>{[address.line1,address.line2,address.landmark,address.city,address.state,address.postal_code].filter(Boolean).join(', ')}</small></span>
        <span className="address-actions">
          {onChoose && <button type="button" className="primary" disabled={saving} onClick={() => onChoose(address, returnTo)}>Use address</button>}
          {!address.is_default && <button type="button" className="secondary" disabled={saving} onClick={() => makeDefault(address)}>Set default</button>}
          <button type="button" className="secondary" aria-label="Edit address" disabled={saving} onClick={() => edit(address)}><Pencil size={14}/></button>
          <button type="button" className="secondary" aria-label="Delete address" disabled={saving} onClick={() => remove(address)}><Trash2 size={14}/></button>
        </span>
      </article>
    )}
    <form className="form address-editor" onSubmit={save}>
      <h3>{editingId ? 'Edit address' : 'Add a delivery address'}</h3>
      <label>Recipient name<input required maxLength={120} value={form.recipient_name} onChange={e=>setForm({...form,recipient_name:e.target.value})}/></label>
      <label>Mobile number<input required type="tel" inputMode="tel" maxLength={30} value={form.phone} onChange={e=>setForm({...form,phone:e.target.value})}/></label>
      <label>House / street address<input required maxLength={200} value={form.line1} onChange={e=>setForm({...form,line1:e.target.value})}/></label>
      <label>Address line 2 (optional)<input maxLength={200} value={form.line2} onChange={e=>setForm({...form,line2:e.target.value})}/></label>
      <label>Landmark<input maxLength={160} value={form.landmark} onChange={e=>setForm({...form,landmark:e.target.value})}/></label>
      <div className="form-two"><label>City<input required value={form.city} onChange={e=>setForm({...form,city:e.target.value})}/></label><label>PIN code (optional)<input inputMode="numeric" maxLength={12} value={form.postal_code} onChange={e=>setForm({...form,postal_code:e.target.value})}/></label></div>
      <div className="form-two"><label>Latitude<input required type="number" min="-90" max="90" step="any" value={form.latitude} onChange={e=>setForm({...form,latitude:e.target.value})}/></label><label>Longitude<input required type="number" min="-180" max="180" step="any" value={form.longitude} onChange={e=>setForm({...form,longitude:e.target.value})}/></label></div>
      <small><MapPin size={13}/> Use map coordinates from your delivery location. Checkout will validate the service distance.</small>
      <label>Delivery instructions (optional)<textarea rows="2" maxLength={500} value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})}/></label>
      <label className="checkbox-label"><input type="checkbox" checked={Boolean(form.is_default)} onChange={e=>setForm({...form,is_default:e.target.checked})}/> Set as my default address</label>
      <button className="primary full" disabled={saving}>{saving ? 'Saving…' : editingId ? 'Save changes' : 'Save address'} <Check size={15}/></button>
      {editingId && <button type="button" className="secondary full" onClick={reset}><X size={14}/> Cancel edit</button>}
    </form>
  </div>
}
