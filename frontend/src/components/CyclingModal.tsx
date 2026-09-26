import React, { useState } from 'react';

interface CyclingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (formattedMessage: string) => void;
}

export const CYCLING_ZONES = [
  { value: 'Zone 1 (Active Recovery < 115 bpm)', label: 'Zone 1 - Active Recovery (< 115 bpm)' },
  { value: 'Zone 2 (Aerobic Base 115-126 bpm)', label: 'Zone 2 - Aerobic Base (Target 115-126 bpm, 60-70% HRR)' },
  { value: 'Zone 3 (Tempo 127-140 bpm)', label: 'Zone 3 - Tempo (127-140 bpm)' },
  { value: 'Zone 4 (Threshold 141-155 bpm)', label: 'Zone 4 - Threshold (141-155 bpm)' },
  { value: 'Zone 5 (VO2 Max 156+ bpm)', label: 'Zone 5 - VO2 Max (156+ bpm)' },
];

export const CyclingModal: React.FC<CyclingModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [durationMinutes, setDurationMinutes] = useState<number>(45);
  const [zone, setZone] = useState<string>('Zone 2 (Aerobic Base 115-126 bpm)');
  const [watts, setWatts] = useState<number>(175);
  const [rpm, setRpm] = useState<number>(88);

  if (!isOpen) return null;

  const handleReset = () => {
    setDurationMinutes(45);
    setZone('Zone 2 (Aerobic Base 115-126 bpm)');
    setWatts(175);
    setRpm(88);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const formattedMessage = `Logged Cycling Ride: ${durationMinutes} mins | ${zone} | Avg Power: ${watts} W | Cadence: ${rpm} RPM`;
    onSubmit(formattedMessage);
    handleClose();
  };

  return (
    <div className="workout-modal-overlay" onClick={handleClose} role="dialog" aria-modal="true">
      <div className="workout-modal-container" onClick={(e) => e.stopPropagation()}>
        <div className="workout-modal-header">
          <div className="workout-modal-title">
            <span className="workout-modal-icon" style={{ fontSize: '24px' }}>🚴</span>
            <h3>Log Cycling Ride (Pooboo Bike)</h3>
          </div>
          <button className="workout-modal-close" onClick={handleClose} aria-label="Close modal">
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit} className="workout-modal-form">
          {/* Duration & Zone Grid */}
          <div className="workout-grid-2col">
            <div className="workout-form-group">
              <label htmlFor="cycling-duration">Duration (Minutes)</label>
              <input
                id="cycling-duration"
                type="number"
                min="1"
                max="300"
                value={durationMinutes}
                onChange={(e) => setDurationMinutes(parseInt(e.target.value) || 1)}
                className="workout-form-control"
                required
              />
            </div>

            <div className="workout-form-group">
              <label htmlFor="cycling-zone">Training Zone</label>
              <select
                id="cycling-zone"
                value={zone}
                onChange={(e) => setZone(e.target.value)}
                className="workout-form-control"
              >
                {CYCLING_ZONES.map((z) => (
                  <option key={z.value} value={z.value}>
                    {z.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Avg Watts & RPM Cadence Grid */}
          <div className="workout-grid-2col">
            <div className="workout-form-group">
              <label htmlFor="cycling-watts">Avg Power (Watts)</label>
              <input
                id="cycling-watts"
                type="number"
                min="0"
                max="1000"
                value={watts}
                onChange={(e) => setWatts(parseInt(e.target.value) || 0)}
                className="workout-form-control"
                required
              />
            </div>

            <div className="workout-form-group">
              <label htmlFor="cycling-rpm">Cadence (RPM)</label>
              <input
                id="cycling-rpm"
                type="number"
                min="0"
                max="250"
                value={rpm}
                onChange={(e) => setRpm(parseInt(e.target.value) || 0)}
                className="workout-form-control"
                required
              />
            </div>
          </div>

          {/* Action Buttons */}
          <div className="workout-modal-actions">
            <button type="button" className="workout-btn-cancel" onClick={handleClose}>
              Cancel
            </button>
            <button type="submit" className="workout-btn-submit">
              Log Cycling Ride
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CyclingModal;
