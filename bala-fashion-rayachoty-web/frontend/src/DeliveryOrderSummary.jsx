import { FiArrowRight } from 'react-icons/fi'

export default function DeliveryOrderSummary({ order, expanded, onToggle }) {
  return (
    <button
      type="button"
      className="delivery-order-summary"
      aria-expanded={expanded}
      aria-label={`${order.order_number}, status ${String(order.status || '').replaceAll('_', ' ')}. ${expanded ? 'Collapse' : 'Expand'} order details`}
      onClick={onToggle}
    >
      <span className="delivery-order-summary-text">
        <b className="delivery-order-number">{order.order_number}</b>
        <small>Status: {String(order.status || 'unknown').replaceAll('_', ' ')}</small>
      </span>
      <FiArrowRight size={18} className={expanded ? 'delivery-order-chevron expanded' : 'delivery-order-chevron'} />
    </button>
  )
}
