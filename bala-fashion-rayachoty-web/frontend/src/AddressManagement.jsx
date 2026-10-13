import { useCallback, useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import { FiCheck, FiMapPin, FiEdit2, FiPlus, FiRefreshCw, FiTrash2, FiX } from 'react-icons/fi'
import { api } from './api'

L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

const RAYACHOTY_MAP_CENTER = [14.057, 78.75]

function AddressLocationPicker({ latitude, longitude, onChange }) {
  const mapNode = useRef(null)
  const mapRef = useRef(null)
  const markerRef = useRef(null)
  const latest = useRef({ latitude, longitude, onChange })
  const [locationError, setLocationError] = useState('')
  latest.current = { latitude, longitude, onChange }

  useEffect(() => {
    let cancelled = false
    const setPoint = (lat, lng) => {
      latest.current.onChange({
        latitude: Number(lat).toFixed(6),
        longitude: Number(lng).toFixed(6),
      })
      setLocationError('')
    }
    const init = () => {
      if (cancelled || !mapNode.current || mapRef.current) return
      const current = latest.current
      const hasPoint = current.latitude !== '' && current.longitude !== '' &&
        Number.isFinite(Number(current.latitude)) && Number.isFinite(Number(current.longitude))
      const center = hasPoint ? [Number(current.latitude), Number(current.longitude)] : RAYACHOTY_MAP_CENTER
      const map = L.map(mapNode.current, { scrollWheelZoom: false }).setView(center, hasPoint ? 16 : 13)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>',
      }).addTo(map)
      const setMarker = (lat, lng) => {
        if (!markerRef.current) {
          markerRef.current = L.marker([lat, lng], { draggable: true }).addTo(map)
          markerRef.current.on('dragend', event => {
            const point = event.target.getLatLng()
            setPoint(point.lat, point.lng)
          })
        } else {
          markerRef.current.setLatLng([lat, lng])
        }
      }
      if (hasPoint) setMarker(center[0], center[1])
      map.on('click', event => {
        setMarker(event.latlng.lat, event.latlng.lng)
        setPoint(event.latlng.lat, event.latlng.lng)
      })
      mapRef.current = map
      map.__setMarker = setMarker
      map.whenReady(() => { if (!cancelled) map.invalidateSize() })
    }
    init()
    return () => {
      cancelled = true
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
        markerRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const lat = Number(latitude)
    const lng = Number(longitude)
    if (latitude !== '' && longitude !== '' && Number.isFinite(lat) && Number.isFinite(lng)) {
      map.__setMarker?.(lat, lng)
      map.setView([lat, lng], 16)
    } else if (markerRef.current) {
      map.removeLayer(markerRef.current)
      markerRef.current = null
    }
  }, [latitude, longitude])

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setLocationError('Location is not supported. Tap the map to place a pin.')
      return
    }
    setLocationError('Finding your current location…')
    navigator.geolocation.getCurrentPosition(
      position => {
        latest.current.onChange({
          latitude: position.coords.latitude.toFixed(6),
          longitude: position.coords.longitude.toFixed(6),
        })
        setLocationError('')
      },
      () => setLocationError('Could not get your location. Allow location access or tap the map to place a pin.'),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 },
    )
  }

  return <section className="location-picker address-location-picker">
    <div className="location-picker-head">
      <b>Pin your delivery location</b>
      <button type="button" className="secondary" onClick={useCurrentLocation}><FiMapPin size={15}/> Use my location</button>
    </div>
    <p>Tap the map or drag the pin to your house entrance. The pin coordinates are saved with this address.</p>
    <div ref={mapNode} className="location-map" role="application" aria-label="Delivery address map" />
    <div className="location-coordinates">
      <span>Latitude: {latitude || 'Not selected'}</span>
      <span>Longitude: {longitude || 'Not selected'}</span>
    </div>
    {locationError && <small className="location-error">{locationError}</small>}
    <small>Map data &copy; OpenStreetMap contributors.</small>
  </section>
}

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
      <button type="button" className="secondary" onClick={load} disabled={loading}><FiRefreshCw size={14}/> Refresh</button>
    </div>
    {error && <div className="warning">{error}</div>}
    {loading ? <p>Loading saved addresses…</p> : !addresses.length ? <p className="seller-empty">No saved addresses yet. Add one below.</p> : addresses.map(address =>
      <article className="seller-store-row saved-address-row" key={address.id}>
        <span><b>{address.recipient_name} {address.is_default && <small className="seller-status approved">Default</small>}</b><small>{address.phone}</small><small>{[address.line1,address.line2,address.landmark,address.city,address.state,address.postal_code].filter(Boolean).join(', ')}</small></span>
        <span className="address-actions">
          {onChoose && <button type="button" className="primary" disabled={saving} onClick={() => onChoose(address, returnTo)}>Use address</button>}
          {!address.is_default && <button type="button" className="secondary" disabled={saving} onClick={() => makeDefault(address)}>Set default</button>}
          <button type="button" className="secondary" aria-label="Edit address" disabled={saving} onClick={() => edit(address)}><FiEdit2 size={14}/></button>
          <button type="button" className="secondary" aria-label="Delete address" disabled={saving} onClick={() => remove(address)}><FiTrash2 size={14}/></button>
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
      <AddressLocationPicker
        latitude={form.latitude}
        longitude={form.longitude}
        onChange={({ latitude, longitude }) => setForm(current => ({ ...current, latitude, longitude }))}
      />
      {(!form.latitude || !form.longitude) && <small className="location-error">Select a pin on the map or use your current location before saving.</small>}
      <label>Delivery instructions (optional)<textarea rows="2" maxLength={500} value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})}/></label>
      <label className="checkbox-label"><input type="checkbox" checked={Boolean(form.is_default)} onChange={e=>setForm({...form,is_default:e.target.checked})}/> Set as my default address</label>
      <button className="primary full" disabled={saving}>{saving ? 'Saving…' : editingId ? 'Save changes' : 'Save address'} <FiCheck size={15}/></button>
      {editingId && <button type="button" className="secondary full" onClick={reset}><FiX size={14}/> Cancel edit</button>}
    </form>
  </div>
}
