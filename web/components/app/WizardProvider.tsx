"use client";

import {
  createContext,
  useContext,
  useReducer,
  type ReactNode,
  type Dispatch,
} from "react";

export type Step =
  | "IDLE"
  | "RUNNING"
  | "PACKAGE_SELECT"
  | "PIN_REVIEW"
  | "GENERATING"
  | "DONE"
  | "ERROR";

export interface PinInfo {
  number: string;
  name: string;
  pin_type: string;
  description: string;
  alt_numbers: string[];
}

export interface PackageCandidate {
  name: string;
  pin_count: number;
  ti_code: string;
}

export interface MatchResult {
  symbol_lib: string;
  symbol_name: string;
  footprint_lib: string;
  footprint_name: string;
  symbol_score: number;
  footprint_score: number;
  pin_mapping: Record<string, string>;
}

export interface DatasheetSummary {
  part_number: string;
  manufacturer: string;
  description: string;
  component_type: string;
  package: PackageCandidate | null;
  datasheet_url: string;
  confidence: number;
  pins: PinInfo[];
}

export interface FileInfo {
  filename: string;
  size_bytes: number;
}

export interface ModelInfo {
  ref: string;
  inferred: boolean;
}

export interface DetectedProject {
  dir: string;
  name: string;
}

export interface WizardState {
  step: Step;
  jobId: string;
  partNumber: string;
  candidates: PackageCandidate[];
  datasheet: DatasheetSummary | null;
  match: MatchResult | null;
  pins: PinInfo[];
  files: FileInfo[];
  model: ModelInfo | null;
  error: string;
  logs: string[];
  selectedPinNumber: string | null;
  detectedProject: DetectedProject | null;
}

export type WizardAction =
  | { type: "START_RUN"; jobId: string; partNumber: string }
  | { type: "ADD_LOG"; message: string }
  | {
      type: "COMPLETE";
      datasheet: DatasheetSummary;
      match: MatchResult;
      pins: PinInfo[];
      candidates: PackageCandidate[];
    }
  | {
      type: "SWITCH_PACKAGE";
      datasheet: DatasheetSummary;
      match: MatchResult;
      pins: PinInfo[];
    }
  | { type: "UPDATE_PIN"; index: number; field: string; value: string }
  | { type: "SELECT_PIN"; pinNumber: string | null }
  | { type: "START_GENERATE" }
  | { type: "GENERATED"; files: FileInfo[]; model: ModelInfo | null; imported?: boolean }
  | { type: "DETECT_PROJECT"; project: DetectedProject | null }
  | { type: "ERROR"; message: string }
  | { type: "RESET" };

const initialState: WizardState = {
  step: "IDLE",
  jobId: "",
  partNumber: "",
  candidates: [],
  datasheet: null,
  match: null,
  pins: [],
  files: [],
  model: null,
  error: "",
  logs: [],
  selectedPinNumber: null,
  detectedProject: null,
};

function reducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case "START_RUN":
      return {
        ...initialState,
        step: "RUNNING",
        jobId: action.jobId,
        partNumber: action.partNumber,
      };
    case "ADD_LOG":
      return { ...state, logs: [...state.logs, action.message] };
    case "COMPLETE": {
      const needsPackageSelect =
        action.candidates.length > 1 && !action.datasheet.package;
      return {
        ...state,
        step: needsPackageSelect ? "PACKAGE_SELECT" : "PIN_REVIEW",
        datasheet: action.datasheet,
        match: action.match,
        pins: action.pins,
        candidates: action.candidates,
      };
    }
    case "SWITCH_PACKAGE":
      return {
        ...state,
        step: "PIN_REVIEW",
        datasheet: action.datasheet,
        match: action.match,
        pins: action.pins,
        selectedPinNumber: null,
      };
    case "UPDATE_PIN": {
      const pins = [...state.pins];
      pins[action.index] = { ...pins[action.index], [action.field]: action.value };
      return { ...state, pins };
    }
    case "SELECT_PIN":
      return { ...state, selectedPinNumber: action.pinNumber };
    case "START_GENERATE":
      return { ...state, step: "GENERATING" };
    case "GENERATED":
      return {
        ...state,
        step: action.imported ? "DONE" : "DONE",
        files: action.files,
        model: action.model,
      };
    case "DETECT_PROJECT":
      return { ...state, detectedProject: action.project };
    case "ERROR":
      return { ...state, step: "ERROR", error: action.message };
    case "RESET":
      return { ...initialState, detectedProject: state.detectedProject };
    default:
      return state;
  }
}

const WizardContext = createContext<WizardState>(initialState);
const WizardDispatchContext = createContext<Dispatch<WizardAction>>(() => {});

export function WizardProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <WizardContext.Provider value={state}>
      <WizardDispatchContext.Provider value={dispatch}>
        {children}
      </WizardDispatchContext.Provider>
    </WizardContext.Provider>
  );
}

export function useWizard() {
  return useContext(WizardContext);
}

export function useWizardDispatch() {
  return useContext(WizardDispatchContext);
}
