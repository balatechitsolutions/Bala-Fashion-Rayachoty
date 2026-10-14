import { useState } from 'react'
import { FiMapPin, FiNavigation, FiSave } from 'react-icons/fi'
import { api } from './api'

const fields = [
  ['recipient_name', 'Recipient name', true],
  ['phone', 'Customer mobile number', true],
  ['line1', 'House / street address', true],
  ['line2', 'Address line 2 (optional)', false],
  ['landmark', 'Landmark (optional)', false],
  ['postal_code', 'PIN code (optional)', false],
]

export function OrderAddressRepair({ session, order, role, onSaved, notify }) {
  const current = order?.address_snapshot || {}
  const [form, setForm] = useState(() => ({
    recipient_name: current.recipient_name || '',
    phone: current.phone || '',
    line1: current.line1 || '',
    line2: current.line2 || '',
    landmark: current.landmark || '',
    city: current.city || 'Rayachoty',
    state: current.state || 'Andhra Pradesh',
    postal_code: current.postal_code || '',
    latitude: current.latitude == null ? '' : String(current.latitude),
    longitude: current.longitude == null ? '' : String(current.longitude),
    correction_reason: '',
  }))
  const [saving, setSaving] = useState(false)
  const [locating, setLocating] = useState(false)
  function update(key, value) { setForm(previous => ({ ...previous, [key]: value })) }
  function useCurrentLocation() {
    if (!navigator.geolocation) return notify('This device does not support location access. Select coordinates on the checkout map.')
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      position => {
        setForm(previous => ({ ...previous, latitude: String(position.coords.latitude), longitude: String(position.coords.longitude) }))
        setLocating(false)
        notify('Delivery location captured. Save the address to continue.')
      },
      () => { setLocating(false); notify('Location access failed. Allow location permission and try again.') },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }
    )
  }
  async function submit(event) {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    try {
      const result = await api('/orders/repair-address/', {
        method: 'PATCH',
        token: session.access_token,
        body: JSON.stringify({ order_id: order.id, ...form, replace_existing: role === 'admin' }),
      })
      onSaved?.(result.address_snapshot)
      notify('Delivery address saved. The order will be checked again before delivery starts.')
    } catch (error) {
      notify(error.message || 'Could not save delivery address.')
    } finally { setSaving(false) }
  }
  return <form className="form order-address-repair" onSubmit={submit}>
    <div className="notice"><b>Complete delivery details</b><p>Enter verified contact and address details. Delivery remains blocked until the address and map location are complete.</p></div>
    {fields.map(([key, label, required]) => <label key={key}>{label}<input value={form[key]} required={required} maxLength={key === 'line1' ? 200 : 160} inputMode={key === 'phone' ? 'tel' : undefined} onChange={event => update(key, event.target.value)} /></label>)}
    {role === 'admin' && <label>Correction reason<input value={form.correction_reason} required maxLength={500} onChange={event => update('correction_reason', event.target.value)} placeholder="Why this saved order address needs correction" /></label>}
    <div className="form-two">
      <label>Latitude<input required type="number" min="-90" max="90" step="any" value={form.latitude} onChange={event => update('latitude', event.target.value)} /></label>
      <label>Longitude<input required type="number" min="-180" max="180" step="any" value={form.longitude} onChange={event => update('longitude', event.target.value)} /></label>
    </div>
    <button type="button" className="secondary full" onClick={useCurrentLocation} disabled={locating}><FiNavigation size={15}/>{locating ? 'Getting location…' : 'Use current location'}</button>
    <button type="submit" className="primary full" disabled={saving}><FiSave size={15}/>{saving ? 'Saving…' : role === 'admin' ? 'Save corrected order address' : 'Complete my delivery address'}</button>
  </form>
}
