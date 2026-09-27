import React, { useState } from 'react';

interface WorkoutModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (formattedMessage: string) => void;
}

export const WORKOUT_EXERCISES = [
  'Goblet Squats (Pause)',
  'Turkish Get-Ups',
  'Kettlebell Swings (Single-Arm)',
  'Kettlebell Halos',
  'Single-Arm Overhead Press',
  'Rotational Lunges',
  'Suitcase Carries',
  'Dumbbell Lateral Raises',
  'Dumbbell Bicep Curls',
  'Dumbbell Overhead Press',
  'Dumbbell Romanian Deadlifts',
  'Circular Balance Board Stability Drill',
  'Calf Stretcher Mobility & Plantar Stretch',
  'Yoga Mat Mobility & Core Flow',
  'Custom Entry'
];

export const EQUIPMENT_OPTIONS = [
  '15 lb Kettlebell',
  'Dumbbells (12 lbs)',
  'Dumbbells (10 lbs)',
  'Dumbbells (8 lbs)',
  'Dumbbells (5 lbs)',
  'Dumbbells (3 lbs)',
  'Circular Balance Board',
  'Calf Stretcher',
  'Yoga Mat / Bodyweight'
];

export const WorkoutModal: React.FC<WorkoutModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [selectedExercise, setSelectedExercise] = useState('Goblet Squats (Pause)');
  const [customExercise, setCustomExercise] = useState('');
  const [selectedEquipment, setSelectedEquipment] = useState('15 lb Kettlebell');
  const [weightLbs, setWeightLbs] = useState<number>(15);
  const [completedRecommended, setCompletedRecommended] = useState(true);
  const [targetSets, setTargetSets] = useState<number>(4);
  const [actualSets, setActualSets] = useState<number>(4);
  const [targetReps, setTargetReps] = useState<number>(10);
  const [actualReps, setActualReps] = useState<number>(10);
  const [durationMinutes, setDurationMinutes] = useState<number>(25);
  const [rpe, setRpe] = useState<number>(8);

  if (!isOpen) return null;

  const handleReset = () => {
    setSelectedExercise('Goblet Squats (Pause)');
    setCustomExercise('');
    setSelectedEquipment('15 lb Kettlebell');
    setWeightLbs(15);
    setCompletedRecommended(true);
    setTargetSets(4);
    setActualSets(4);
    setTargetReps(10);
    setActualReps(10);
    setDurationMinutes(25);
    setRpe(8);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  const handleEquipmentChange = (equip: string) => {
    setSelectedEquipment(equip);
    if (equip.includes('15 lb')) setWeightLbs(15);
    else if (equip.includes('12 lbs')) setWeightLbs(12);
    else if (equip.includes('10 lbs')) setWeightLbs(10);
    else if (equip.includes('8 lbs')) setWeightLbs(8);
    else if (equip.includes('5 lbs')) setWeightLbs(5);
    else if (equip.includes('3 lbs')) setWeightLbs(3);
    else if (equip.includes('Balance') || equip.includes('Stretcher') || equip.includes('Mat')) setWeightLbs(0);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const exerciseName = selectedExercise === 'Custom Entry' && customExercise.trim()
      ? customExercise.trim()
      : selectedExercise;

    const completedStatus = completedRecommended && (actualSets >= targetSets && actualReps >= targetReps)
      ? 'Yes'
      : 'Partial';

    const formattedMessage = `Logged Workout: ${exerciseName} | Equipment: ${selectedEquipment} | Weight: ${weightLbs} lbs | Completed: ${completedStatus} | Sets: ${actualSets}/${targetSets} | Reps: ${actualReps}/${targetReps} | Duration: ${durationMinutes} mins | RPE: ${rpe}`;

    onSubmit(formattedMessage);
    handleClose();
  };

  return (
    <div className="workout-modal-overlay" onClick={handleClose} role="dialog" aria-modal="true">
      <div className="workout-modal-container" onClick={(e) => e.stopPropagation()}>
        <div className="workout-modal-header">
          <div className="workout-modal-title">
            <span className="workout-modal-icon">🏋️‍♂️</span>
            <h3>Log Strength & Mobility Workout</h3>
          </div>
          <button className="workout-modal-close" onClick={handleClose} aria-label="Close modal">
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit} className="workout-modal-form">
          {/* Exercise Selection */}
          <div className="workout-form-group">
            <label htmlFor="exercise-select">Exercise Movement</label>
            <select
              id="exercise-select"
              value={selectedExercise}
              onChange={(e) => setSelectedExercise(e.target.value)}
              className="workout-form-control"
            >
              {WORKOUT_EXERCISES.map((ex) => (
                <option key={ex} value={ex}>{ex}</option>
              ))}
            </select>
          </div>

          {selectedExercise === 'Custom Entry' && (
            <div className="workout-form-group">
              <label htmlFor="custom-exercise">Custom Movement Name</label>
              <input
                id="custom-exercise"
                type="text"
                value={customExercise}
                onChange={(e) => setCustomExercise(e.target.value)}
                placeholder="e.g., Dumbbell Lateral Raise, Balance Squat"
                className="workout-form-control"
                required
              />
            </div>
          )}

          {/* Equipment & Weight Selection */}
          <div className="workout-grid-2col">
            <div className="workout-form-group">
              <label htmlFor="equipment-select">Equipment Used</label>
              <select
                id="equipment-select"
                value={selectedEquipment}
                onChange={(e) => handleEquipmentChange(e.target.value)}
                className="workout-form-control"
              >
                {EQUIPMENT_OPTIONS.map((equip) => (
                  <option key={equip} value={equip}>{equip}</option>
                ))}
              </select>
            </div>

            <div className="workout-form-group">
              <label htmlFor="workout-weight">Weight (lbs)</label>
              <input
                id="workout-weight"
                type="number"
                min="0"
                max="100"
                step="0.5"
                value={weightLbs}
                onChange={(e) => setWeightLbs(parseFloat(e.target.value) || 0)}
                className="workout-form-control"
              />
            </div>
          </div>

          {/* Completion Toggle */}
          <div className="workout-toggle-container">
            <label className="workout-toggle-label">
              <input
                type="checkbox"
                checked={completedRecommended}
                onChange={(e) => {
                  setCompletedRecommended(e.target.checked);
                  if (e.target.checked) {
                    setActualSets(targetSets);
                    setActualReps(targetReps);
                  }
                }}
              />
              <span className="workout-toggle-text">Completed Recommended Routine?</span>
            </label>
          </div>

          {/* Sets & Reps Grid */}
          <div className="workout-grid-2col">
            <div className="workout-form-group">
              <label htmlFor="target-sets">Target Sets</label>
              <input
                id="target-sets"
                type="number"
                min="1"
                max="20"
                value={targetSets}
                onChange={(e) => {
                  const val = parseInt(e.target.value) || 1;
                  setTargetSets(val);
                  if (completedRecommended) setActualSets(val);
                }}
                className="workout-form-control"
              />
            </div>

            <div className="workout-form-group">
              <label htmlFor="actual-sets">Actual Sets Completed</label>
              <input
                id="actual-sets"
                type="number"
                min="0"
                max="20"
                value={actualSets}
                onChange={(e) => setActualSets(parseInt(e.target.value) || 0)}
                className="workout-form-control"
              />
            </div>
          </div>

          <div className="workout-grid-2col">
            <div className="workout-form-group">
              <label htmlFor="target-reps">Target Reps / Set</label>
              <input
                id="target-reps"
                type="number"
                min="1"
                max="100"
                value={targetReps}
                onChange={(e) => {
                  const val = parseInt(e.target.value) || 1;
                  setTargetReps(val);
                  if (completedRecommended) setActualReps(val);
                }}
                className="workout-form-control"
              />
            </div>

            <div className="workout-form-group">
              <label htmlFor="actual-reps">Actual Reps Completed</label>
              <input
                id="actual-reps"
                type="number"
                min="0"
                max="100"
                value={actualReps}
                onChange={(e) => setActualReps(parseInt(e.target.value) || 0)}
                className="workout-form-control"
              />
            </div>
          </div>

          {/* Duration & Intensity RPE */}
          <div className="workout-grid-2col">
            <div className="workout-form-group">
              <label htmlFor="workout-duration">Duration (Minutes)</label>
              <input
                id="workout-duration"
                type="number"
                min="1"
                max="180"
                value={durationMinutes}
                onChange={(e) => setDurationMinutes(parseInt(e.target.value) || 1)}
                className="workout-form-control"
              />
            </div>

            <div className="workout-form-group">
              <label htmlFor="workout-rpe">
                RPE Intensity (1–10): <strong style={{ color: 'var(--accent-orange)' }}>{rpe}</strong>
              </label>
              <input
                id="workout-rpe"
                type="range"
                min="1"
                max="10"
                step="1"
                value={rpe}
                onChange={(e) => setRpe(parseInt(e.target.value))}
                className="workout-range-slider"
              />
            </div>
          </div>

          {/* Action Buttons */}
          <div className="workout-modal-actions">
            <button type="button" className="workout-btn-cancel" onClick={handleClose}>
              Cancel
            </button>
            <button type="submit" className="workout-btn-submit">
              Log Workout
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default WorkoutModal;

