import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeftIcon,
  CalendarIcon,
  TableCellsIcon,
  ArrowDownTrayIcon,
  ClockIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  XCircleIcon,
} from "@heroicons/react/24/outline";
import CalendarView from "../components/CalendarView";
import toast from "react-hot-toast";

const API_HOST =
  process.env.REACT_APP_API_HOST || "http://localhost:8000";

const ScheduleViewerPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [scheduleData, setScheduleData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState("calendar");
  const [crnColors, setCrnColors] = useState({});
  const [progress, setProgress] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [cooldownMode, setCooldownMode] = useState(false);

  useEffect(() => {
    if (id) {
      checkScheduleStatus();
      // Set up polling for status updates
      const interval = setInterval(checkScheduleStatus, 3000);
      return () => clearInterval(interval);
    }
  }, [id]);

  const checkScheduleStatus = async () => {
    try {
      const response = await fetch(`${API_HOST}/api/schedule/${id}`);
      const data = await response.json();

      if (!response.ok) {
        if (response.status === 404) {
          setError("Schedule not found");
          setLoading(false);
          return;
        }
        throw new Error(data.error || "Failed to fetch schedule status");
      }

      setScheduleData(data);
      setProgress(data.progress);
      setTimeline(data.timeline || []);
      setCooldownMode(data.cooldown_mode || false);

      // If processing is complete, stop polling
      if (data.status === "done_processing" || data.status === "ai_failed" || data.status === "extraction_failed") {
        setLoading(false);
        if (data.schedule && data.schedule.classes) {
          generateColors(data.schedule);
        }
      } else {
        setLoading(true);
      }

    } catch (error) {
      console.error("Error checking schedule status:", error);
      setError("Failed to check schedule status");
      setLoading(false);
    }
  };

  const generateColors = (schedule) => {
    if (!schedule || !schedule.classes) return;

    const colors = [
      "#FECACA", "#BFDBFE", "#BBF7D0", "#FEF08A", "#E9D5FF",
      "#FBCFE8", "#C7D2FE", "#99F6E4", "#FED7AA", "#A5F3FC",
      "#D9F99D", "#FDE68A", "#A7F3D0", "#DDD6FE", "#F5D0FE",
    ];

    const crnColorMap = {};
    schedule.classes.forEach((cls, index) => {
      if (!crnColorMap[cls.crn]) {
        crnColorMap[cls.crn] = colors[index % colors.length];
      }
    });

    setCrnColors(crnColorMap);
  };

  const handleDownload = async () => {
    try {
      toast.loading("Preparing download...", { id: "download" });

      if (!scheduleData || !scheduleData.schedule || !scheduleData.schedule.classes || scheduleData.schedule.classes.length === 0) {
        toast.error("No schedule data to download", { id: "download" });
        return;
      }

      // Convert color hex values to RGB format for matplotlib
      const colorMapping = {};
      Object.keys(crnColors).forEach((crn) => {
        const hex = crnColors[crn].replace("#", "");
        const r = parseInt(hex.substring(0, 2), 16) / 255;
        const g = parseInt(hex.substring(2, 4), 16) / 255;
        const b = parseInt(hex.substring(4, 6), 16) / 255;
        colorMapping[crn] = [r, g, b];
      });

      const response = await fetch(`${API_HOST}/api/download_schedule/${id}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          crnColors: colorMapping,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to download schedule");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `schedule-${id}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      toast.success("Download started!", { id: "download" });
    } catch (error) {
      console.error("Download error:", error);
      toast.error("Failed to download schedule", { id: "download" });
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case "done_processing":
        return <CheckCircleIcon className="h-6 w-6 text-green-500" />;
      case "ai_failed":
      case "extraction_failed":
        return <XCircleIcon className="h-6 w-6 text-red-500" />;
      default:
        return <ClockIcon className="h-6 w-6 text-blue-500 animate-spin" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case "done_processing":
        return "text-green-600 bg-green-50 border-green-200";
      case "ai_failed":
      case "extraction_failed":
        return "text-red-600 bg-red-50 border-red-200";
      default:
        return "text-blue-600 bg-blue-50 border-blue-200";
    }
  };

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <XCircleIcon className="h-16 w-16 text-red-500 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
            Error
          </h2>
          <p className="text-gray-600 dark:text-gray-400 mb-6">{error}</p>
          <button
            onClick={() => navigate("/scheduler")}
            className="inline-flex items-center px-4 py-2 bg-[#861F41] hover:bg-[#6B1934] text-white font-medium rounded-lg transition-colors"
          >
            <ArrowLeftIcon className="h-4 w-4 mr-2" />
            Back to Scheduler
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Header */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 mb-8">
            <div className="flex items-center mb-4">
              <button
                onClick={() => navigate("/scheduler")}
                className="mr-4 p-2 text-gray-600 dark:text-gray-400 hover:text-[#861F41] dark:hover:text-[#E5751F] hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                <ArrowLeftIcon className="h-5 w-5" />
              </button>
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                  Schedule Status
                </h1>
                <p className="text-gray-600 dark:text-gray-400">
                  Request ID: {id}
                </p>
              </div>
            </div>
          </div>

          {/* Progress Section */}
          {progress && (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 mb-8">
              <div className="flex items-center mb-4">
                {getStatusIcon(scheduleData?.status)}
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white ml-3">
                  {progress.stage}
                </h2>
              </div>
              
              <div className="mb-4">
                <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400 mb-2">
                  <span>{progress.message}</span>
                  <span>{progress.percentage}%</span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                  <div
                    className="bg-[#861F41] dark:bg-[#E5751F] h-2 rounded-full transition-all duration-500"
                    style={{ width: `${progress.percentage}%` }}
                  ></div>
                </div>
              </div>

              {cooldownMode && (
                <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
                  <div className="flex items-center">
                    <ExclamationCircleIcon className="h-5 w-5 text-yellow-600 dark:text-yellow-400 mr-2" />
                    <p className="text-yellow-800 dark:text-yellow-200 text-sm">
                      Service is currently in cooldown mode. Your request will be processed when the service becomes available.
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Timeline Section */}
          {timeline.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Timeline
              </h3>
              <div className="space-y-4">
                {timeline.map((event, index) => (
                  <div key={index} className="flex items-start">
                    <div className="flex-shrink-0 w-3 h-3 bg-[#861F41] dark:bg-[#E5751F] rounded-full mt-1.5"></div>
                    <div className="ml-4">
                      <p className="text-sm font-medium text-gray-900 dark:text-white">
                        {event.event}
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        {event.description}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-500">
                        {new Date(event.time).toLocaleString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Schedule is ready
  const schedule = scheduleData?.schedule;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 mb-8">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between">
            <div className="flex items-center mb-4 md:mb-0">
              <button
                onClick={() => navigate("/scheduler")}
                className="mr-4 p-2 text-gray-600 dark:text-gray-400 hover:text-[#861F41] dark:hover:text-[#E5751F] hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                <ArrowLeftIcon className="h-5 w-5" />
              </button>
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                  Your Schedule
                </h1>
                <p className="text-gray-600 dark:text-gray-400">
                  Request ID: {id}
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={handleDownload}
                className="inline-flex items-center px-4 py-2 bg-[#861F41] hover:bg-[#6B1934] text-white font-medium rounded-lg transition-colors"
              >
                <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                Download PDF
              </button>
            </div>
          </div>
        </div>

        {/* View Toggle */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4 mb-8">
          <div className="flex items-center justify-center space-x-4">
            <button
              onClick={() => setViewMode("calendar")}
              className={`inline-flex items-center px-4 py-2 rounded-lg font-medium transition-colors ${
                viewMode === "calendar"
                  ? "bg-[#861F41] text-white"
                  : "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600"
              }`}
            >
              <CalendarIcon className="h-4 w-4 mr-2" />
              Calendar View
            </button>
            <button
              onClick={() => setViewMode("table")}
              className={`inline-flex items-center px-4 py-2 rounded-lg font-medium transition-colors ${
                viewMode === "table"
                  ? "bg-[#861F41] text-white"
                  : "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600"
              }`}
            >
              <TableCellsIcon className="h-4 w-4 mr-2" />
              Table View
            </button>
          </div>
        </div>

        {/* Schedule Content */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          {/* Check if schedule is empty or has no classes */}
          {!schedule || !schedule.classes || schedule.classes.length === 0 ? (
            <div className="text-center py-12">
              <div className="mx-auto w-16 h-16 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center mb-4">
                <CalendarIcon className="h-8 w-8 text-gray-400" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                No Schedule Found
              </h3>
              <p className="text-gray-600 dark:text-gray-400 mb-6 max-w-md mx-auto">
                It seems no valid schedule could be generated with your current
                course selections and preferences.
              </p>
              <div className="space-y-3">
                <p className="text-sm text-gray-500 dark:text-gray-500">
                  <strong>Possible reasons:</strong>
                </p>
                <ul className="text-sm text-gray-500 dark:text-gray-500 space-y-1 max-w-md mx-auto text-left">
                  <li>• Course conflicts with your preferences</li>
                  <li>• No available sections for selected courses</li>
                  <li>• Time constraints are too restrictive</li>
                  <li>• Professor preferences are unavailable</li>
                </ul>
              </div>
              <div className="mt-8 space-y-3">
                <button
                  onClick={() => navigate("/scheduler")}
                  className="inline-flex items-center px-6 py-3 bg-[#861F41] hover:bg-[#6B1934] text-white font-medium rounded-lg transition-colors"
                >
                  <ArrowLeftIcon className="h-4 w-4 mr-2" />
                  Try Different Options
                </button>
                <div className="text-xs text-gray-400 dark:text-gray-500">
                  Try adjusting your course selections, preferences, or semester
                </div>
              </div>
            </div>
          ) : (
            <>
              {viewMode === "calendar" ? (
                <CalendarView schedule={schedule} setCrnColors={setCrnColors} />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse">
                    <thead>
                      <tr className="bg-gray-50 dark:bg-gray-700">
                        <th className="border border-gray-300 dark:border-gray-600 p-3 text-left font-semibold text-gray-900 dark:text-white">
                          Course
                        </th>
                        <th className="border border-gray-300 dark:border-gray-600 p-3 text-left font-semibold text-gray-900 dark:text-white">
                          Course Name
                        </th>
                        <th className="border border-gray-300 dark:border-gray-600 p-3 text-left font-semibold text-gray-900 dark:text-white">
                          CRN
                        </th>
                        <th className="border border-gray-300 dark:border-gray-600 p-3 text-left font-semibold text-gray-900 dark:text-white">
                          Instructor
                        </th>
                        <th className="border border-gray-300 dark:border-gray-600 p-3 text-left font-semibold text-gray-900 dark:text-white">
                          Schedule
                        </th>
                        <th className="border border-gray-300 dark:border-gray-600 p-3 text-left font-semibold text-gray-900 dark:text-white">
                          Location
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {schedule.classes.map((cls, index) => (
                        <tr
                          key={index}
                          className="hover:bg-gray-50 dark:hover:bg-gray-700"
                        >
                          <td className="border border-gray-300 dark:border-gray-600 p-3">
                            <div className="font-medium text-gray-900 dark:text-white">
                              {cls.courseNumber}
                            </div>
                          </td>
                          <td className="border border-gray-300 dark:border-gray-600 p-3">
                            <div className="text-gray-700 dark:text-gray-300">
                              {cls.courseName}
                            </div>
                          </td>
                          <td className="border border-gray-300 dark:border-gray-600 p-3">
                            <div className="text-gray-600 dark:text-gray-400">
                              {cls.crn}
                            </div>
                          </td>
                          <td className="border border-gray-300 dark:border-gray-600 p-3">
                            <div className="text-gray-700 dark:text-gray-300">
                              {cls.professorName}
                            </div>
                          </td>
                          <td className="border border-gray-300 dark:border-gray-600 p-3">
                            <div className="text-gray-700 dark:text-gray-300">
                              {cls.time} on {cls.days}
                            </div>
                          </td>
                          <td className="border border-gray-300 dark:border-gray-600 p-3">
                            <div className="text-gray-700 dark:text-gray-300">
                              {cls.location}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ScheduleViewerPage;